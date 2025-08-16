import zipxz as zipfile

class ArchiveIO:
    def __init__(self, file, mode, compression="store"):
        self._file = file
        self._mode = mode
        
        compression_map = {
            "deflate": zipfile.ZIP_DEFLATED,
            "bzip2": zipfile.ZIP_BZIP2,
            "lzma": zipfile.ZIP_LZMA,
            "store": zipfile.ZIP_STORED,
            "xz": zipfile.ZIP_XZ,
        }

        if compression.lower() not in compression_map:
            raise ValueError(f"Unsupported compression: {compression}")

        self._compression = compression_map[compression.lower()]

        try:
            self._archive = zipfile.ZipFile(file, mode, compression=self._compression)
        except NotImplementedError as e:
            raise ValueError(f"LZMA compression not supported in your Python build: {e}")
        except Exception as e:
            raise ValueError(f"Failed to open the archive: {e}")

    def file_exists(self, name: str) -> bool:
        return name in self._archive.namelist()

    def file_read(self, name: str) -> str:
        try:
            return self._archive.read(name).decode("utf-8")
        except KeyError:
            raise FileNotFoundError(f"The file '{name}' does not exist in the archive.")

    def namelist(self) -> list:
        return self._archive.namelist()

    def close(self) -> None:
        self._archive.close()
