from joblib import Memory
import deepdrr

joblib_cache = deepdrr.utils.data_utils.deepdrr_data_dir()/"joblib_cache"
joblib_cache.mkdir(parents=True, exist_ok=True)
memory = Memory(joblib_cache, verbose=9999)

@memory.cache
def from_nifti_cached(*args, **kwargs):
    return deepdrr.Volume.from_nifti(*args, **kwargs)

@memory.cache
def from_meshes_cached(*args, **kwargs):
    return deepdrr.Volume.from_meshes(*args, **kwargs)
