import zipfile
import lzma
import inspect

from ._patcher import patch

zipfile.ZIP_XZ = 95
zipfile.compressor_names[zipfile.ZIP_XZ] = 'xz'
zipfile.XZ_VERSION = 63

@patch(zipfile, '_check_compression')
def zstd_check_compression(compression):
    if compression == zipfile.ZIP_XZ:
        pass
    else:
        patch.originals['_check_compression'](compression)


@patch(zipfile, '_get_decompressor')
def zstd_get_decompressor(compress_type):
    if compress_type == zipfile.ZIP_XZ:
        return lzma.LZMADecompressor(lzma.FORMAT_XZ)
    else:
        return patch.originals['_get_decompressor'](compress_type)


if 'compresslevel' in inspect.signature(zipfile._get_compressor).parameters:
    @patch(zipfile, '_get_compressor')
    def zstd_get_compressor(compress_type, compresslevel=None):
        if compress_type == zipfile.ZIP_XZ:
            return lzma.LZMACompressor(lzma.FORMAT_XZ, preset=compresslevel)
        else:
            return patch.originals['_get_compressor'](compress_type, compresslevel=compresslevel)
else:
    @patch(zipfile, '_get_compressor')
    def zstd_get_compressor(compress_type, compresslevel=None):
        if compress_type == zipfile.ZIP_XZ:
            return lzma.LZMACompressor(lzma.FORMAT_XZ, preset=compresslevel)
        else:
            return patch.originals['_get_compressor'](compress_type)


@patch(zipfile.ZipInfo, 'FileHeader')
def zstd_FileHeader(self, zip64=None):
    if self.compress_type == zipfile.ZIP_XZ:
        self.create_version = max(self.create_version, zipfile.XZ_VERSION)
        self.extract_version = max(self.extract_version, zipfile.XZ_VERSION)
    return patch.originals['FileHeader'](self, zip64=zip64)


