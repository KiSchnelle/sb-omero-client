"""TODO: Add description here."""

import logging
import shutil
from pathlib import Path
from typing import TypeVar

from omero.gateway import (
    BlitzGateway,
    BlitzObjectWrapper,
    DatasetWrapper,
    ImageWrapper,
    ProjectWrapper,
    TagAnnotationWrapper,
)

# init module logger
module_logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BlitzObjectWrapper)


class CustomOMEROClient:
    """A client for interacting with an OMERO server to download datasets."""

    def __init__(  # noqa: PLR0913
        self,
        username: str,
        password: str,
        host: str,
        port: int,
        sync_tag_id: int,
        synced_tag_id: int,
    ) -> None:
        """Initialize the OMEROClient.

        Args:
            username:
                OMERO username.
            password:
                OMERO password.
            host:
                OMERO server hostname or IP address.
            port:
                OMERO server port number.
            sync_tag_id:
                Tag used to mark datasets for synchronization.
            synced_tag_id:
                Tag used to mark datasets that have already been synchronized.

        """
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.sync_tag_id = sync_tag_id
        self.synced_tag_id = synced_tag_id
        self._conn: BlitzGateway | None = None

    def _get_object(
        self,
        *,
        omero_type: str,
        oid: int,
        wrapper_cls: type[T],
    ) -> T:
        conn = self._ensure_connected()

        obj = conn.getObject(omero_type, oid)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if obj is None:
            msg = f"{omero_type} {oid} not found"
            raise ValueError(msg)

        if not isinstance(obj, wrapper_cls):
            msg = f"Object {oid} is not of type {wrapper_cls.__name__}"
            raise TypeError(msg)

        return obj

    def _ensure_connected(
        self,
    ) -> BlitzGateway:
        if self._conn is None:
            msg = "Not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._conn

    def _should_sync(self, dataset: DatasetWrapper) -> bool:
        sync = False
        is_synced = False
        for ann in dataset.listAnnotations():  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(ann, TagAnnotationWrapper):
                ann_id = ann.getId()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                if ann_id == self.sync_tag_id:
                    sync = True
                elif ann_id == self.synced_tag_id:
                    is_synced = True
        return sync and not is_synced

    def _download_image(
        self,
        *,
        img: ImageWrapper,
        out_dir: Path,
    ) -> None:
        file_count = img.countImportedImageFiles()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if not isinstance(file_count, int):
            msg = f"Image {img.getId()} has invalid file count: {file_count}"
            raise TypeError(msg)

        if file_count == 0:
            module_logger.warning(
                "Image has no original files, skipping download.",
            )
            return
        if file_count > 1:
            module_logger.warning(
                "Image has multiple original files (%d), skipping download.",
                file_count,
            )
            return

        original_image = next(img.getImportedImageFiles())
        image_name = original_image.getName()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if not isinstance(image_name, str):
            msg = f"Image {img.getId()} has invalid name type: {image_name}"
            raise TypeError(msg)

        target_file = out_dir / image_name
        module_logger.debug("Downloading image %s to %s", image_name, target_file)

        with target_file.open("wb") as f:
            for chunk in original_image.getFileInChunks():  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(chunk, bytes):
                    msg = f"Chunk is not bytes: {chunk}"
                    raise TypeError(msg)
                f.write(chunk)

    def _tag_dataset_as_synced(
        self,
        *,
        dataset: DatasetWrapper,
    ) -> None:
        """Tag a dataset as synced."""
        tag_annotation = self._get_object(
            omero_type="Annotation",
            oid=532393,
            wrapper_cls=TagAnnotationWrapper,
        )

        if not tag_annotation.canAnnotate():
            msg = f"Annotation {self.synced_tag_id} cannot be used for tagging"
            raise RuntimeError(msg)

        dataset.linkAnnotation(tag_annotation)  # pyright: ignore[reportUnknownMemberType]

    def connect(
        self,
    ) -> None:
        """Connect to the OMERO server.

        Raises:
            RuntimeError:
                If connection to the OMERO server fails.

        """
        self._conn = BlitzGateway(
            username=self.username,
            passwd=self.password,
            host=self.host,
            port=self.port,
        )
        try:
            self._conn.connect()  # pyright: ignore[reportUnknownMemberType]
        except Exception:
            module_logger.exception(
                "Failed to connect to OMERO at %s:%d as %s",
                self.host,
                self.port,
                self.username,
            )
            try:
                self._conn.close()
            except Exception:
                module_logger.exception("Failed to close connection after failure")
            raise

        module_logger.info(
            "Connected to OMERO server at %s:%d as user '%s'",
            self.host,
            self.port,
            self.username,
        )

    def disconnect(
        self,
    ) -> None:
        """Disconnect from the OMERO server."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            module_logger.info("Disconnected from OMERO server")
        else:
            module_logger.warning("No active connection to disconnect")

    def list_datasets_to_sync(
        self,
        *,
        project_id: int,
    ) -> dict[str, int]:
        """List dataset IDs in the project that are marked for synchronization.

        Args:
            project_id:
                The ID of the project to list datasets from.

        Returns:
            A dictionary mapping dataset names to their IDs that
            are marked for synchronization.

        Raises:
            RuntimeError:
                If not connected to the OMERO server.
            ValueError:
                If the project does not exist or has no datasets.
            TypeError:
                If the dataset name or ID is invalid.

        """
        project = self._get_object(
            omero_type="Project",
            oid=project_id,
            wrapper_cls=ProjectWrapper,
        )

        datasets: dict[str, int] = {}
        for dataset in project.listChildren():  # pyright: ignore[reportUnknownMemberType]
            if not isinstance(dataset, DatasetWrapper):
                msg = f"Child object {dataset} of project {project_id} is not a Dataset"
                raise TypeError(msg)

            name = dataset.getName()  # pyright: ignore[reportUnknownVariableType]
            did = dataset.getId()  # pyright: ignore[reportUnknownVariableType]
            if name is None or id is None:
                msg = "Dataset has no name or ID"
                raise ValueError(msg)

            if not isinstance(name, str) or not isinstance(did, int):
                msg = "Dataset has invalid name or ID type"
                raise TypeError(msg)

            if self._should_sync(dataset):
                module_logger.info(
                    "Dataset %s with ID %d is marked for sync",
                    name,
                    did,
                )
                datasets[name] = did
            else:
                module_logger.debug(
                    "Dataset %s with ID %d is not marked for sync",
                    name,
                    did,
                )

        return datasets

    def download_dataset(
        self,
        *,
        dataset_name: str,
        dataset_id: int,
        download_base: Path,
    ) -> None:
        """Download all images in the specified dataset to the given directory.

        Args:
            dataset_name:
                The name of the dataset to download.
            dataset_id:
                The ID of the dataset to download.
            download_base:
                The base directory where the dataset will be downloaded.

        Raises:
            RuntimeError:
                If not connected to the OMERO server.
            ValueError:
                If the dataset does not exist or has no name.
            TypeError:
                If the dataset name is not a string or if child objects are
                not of the expected type.

        """
        dataset = self._get_object(
            omero_type="Dataset",
            oid=dataset_id,
            wrapper_cls=DatasetWrapper,
        )

        out_dir = download_base / dataset_name
        if out_dir.exists():
            module_logger.warning(
                "Output directory %s already exists, overwriting files",
                out_dir,
            )
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(exist_ok=False)
        module_logger.info("Downloading dataset %d to %s", dataset_id, out_dir)

        for img in dataset.listChildren():  # pyright: ignore[reportUnknownMemberType]
            if not isinstance(img, ImageWrapper):
                msg = f"Child object {img} of dataset {dataset_id} is not an Image"
                raise TypeError(msg)

            self._download_image(img=img, out_dir=out_dir)

        module_logger.info(
            "Finished downloading dataset %d to %s",
            dataset_id,
            out_dir,
        )
        self._tag_dataset_as_synced(dataset=dataset)
        module_logger.info(
            "Tagged dataset %d as synced with tag '%s'",
            dataset_id,
            self.synced_tag_id,
        )

    def sync(
        self,
        *,
        project_id: int,
        download_base: Path,
    ) -> None:
        """Synchronize datasets marked for sync."""
        try:
            self.connect()
            datasets = self.list_datasets_to_sync(project_id=project_id)
            module_logger.info(
                "Found %d new datasets to sync in project %d",
                len(datasets),
                project_id,
            )

            if datasets:
                for dataset_name, dataset_id in datasets.items():
                    module_logger.info("Downloading dataset: %s", dataset_name)
                    self.download_dataset(
                        dataset_name=dataset_name,
                        dataset_id=dataset_id,
                        download_base=download_base,
                    )

        finally:
            self.disconnect()
