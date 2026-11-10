"""Loader backend registry: name -> backend class taking its options in the constructor."""

from loaders.base import LoadedDoc, LoaderBackend, LoadFailure, Skip, Sniff, SourceRef
from loaders.filesystem import FilesystemLoader, FilesystemOptions

LOADER_BACKENDS: dict[str, type] = {"filesystem": FilesystemLoader}


def get_loader(name: str, opts: object) -> LoaderBackend:
    try:
        cls = LOADER_BACKENDS[name]
    except KeyError:
        raise ValueError(f"Unknown load backend '{name}'. Known: {', '.join(sorted(LOADER_BACKENDS))}") from None
    return cls(opts)


__all__ = ["LOADER_BACKENDS", "FilesystemLoader", "FilesystemOptions", "LoadFailure", "LoadedDoc",
           "LoaderBackend", "Skip", "Sniff", "SourceRef", "get_loader"]
