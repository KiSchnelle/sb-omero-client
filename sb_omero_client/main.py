"""TODO: Add description here."""

import configparser
import logging
from pathlib import Path

import custom_omero_client

# === Setup logging ===
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
)
module_logger = logging.getLogger(__name__)


def main(
    config_path: Path,
) -> None:
    """Download datasets from an OMERO project.

    Args:
        config_path :
            Path to config file.

    """
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    config = configparser.ConfigParser()
    config.read(config_path)

    omero_user = config.get("omero", "user")
    omero_pass = config.get("omero", "password")
    omero_host = config.get("omero", "host")
    omero_port = config.getint("omero", "port")
    project_id = config.getint("download", "project_id")
    download_folder = Path(config.get("download", "download_folder"))
    sync_tag_id = config.getint("download", "sync_tag_id")
    synced_tag_id = config.getint("download", "synced_tag_id")

    module_logger.info("Starting OMERO Python API downloader...")
    client = custom_omero_client.CustomOMEROClient(
        username=omero_user,
        password=omero_pass,
        host=omero_host,
        port=omero_port,
        sync_tag_id=sync_tag_id,
        synced_tag_id=synced_tag_id,
    )
    module_logger.info("Syncing project %d to folder %s", project_id, download_folder)
    client.sync(
        project_id=project_id,
        download_base=download_folder,
    )


if __name__ == "__main__":
    config_path = Path.home() / ".config" / "sb-omero-client" / "config.ini"

    main(
        config_path=config_path,
    )
