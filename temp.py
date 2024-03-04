import os
from pathlib import Path


BASE_DIRS = {
    'root1': Path(os.environ.get("PATIENT_DATA_DIR", "")).expanduser(),
    'root2': Path.home() / "datasets" / "DeepDRR_DATA"
}

CONSTANTS = {
    'PatientCaseIDPrefix': "case-*",
    'TorsoPrefix': "THIN_BONE_TORSO",
    'PatientMeshLoaderPrefix': "TotalSegmentator_mesh",
    'PatientMeshLoaderMeshname': "body",
    'PatientMeshLoaderSuffix': ".stl",
    'NiftiDRRVolumePrefix': "nifti",
    'NiftiDRRVolumeSuffix': ".nii.gz",
    'PatientAnnoLoaderPrefix': "2023-pelvis-annotations",
    'PatientAnnoLoaderSuffix': ".mrk.json"
}


print(BASE_DIRS['root1'])
print(BASE_DIRS['root2'])


def compute_paths(base_dir, prefixes):
    return {key: base_dir / value / CONSTANTS['TorsoPrefix'] for key, value in prefixes.items()}

prefixes = {
    'mesh_loader': CONSTANTS['PatientMeshLoaderPrefix'],
    'nifti_volume': CONSTANTS['NiftiDRRVolumePrefix'],
    'anno_loader': CONSTANTS['PatientAnnoLoaderPrefix']
}

suffixes = {
    'mesh_loader': CONSTANTS['PatientMeshLoaderMeshname'] + CONSTANTS['PatientMeshLoaderSuffix'],
    'nifti_volume': CONSTANTS['NiftiDRRVolumeSuffix'],
    'anno_loader': CONSTANTS['PatientAnnoLoaderSuffix']
}

paths = compute_paths(BASE_DIRS['root1'], prefixes)


def search_common_cases(paths, prefix):
    common_cases = None
    for path in paths.values():
        case_set = {case_dir.name for case_dir in path.glob(prefix) if case_dir.is_dir()}
        common_cases = case_set if common_cases is None else common_cases & case_set
    return sorted(common_cases)


def search_files_for_cases(common_cases, paths):
    case_files = {}
    for case_id in common_cases:
        case_files[case_id] = {
            file_type: sorted((paths[file_type] / case_id).rglob(f"*{suffixes[file_type]}"))
            for file_type in ['mesh_loader', 'nifti_volume', 'anno_loader']
            if (paths[file_type] / case_id).exists() and (paths[file_type] / case_id).is_dir()
        }
    return case_files


PatientCaseID = search_common_cases(paths, CONSTANTS['PatientCaseIDPrefix'])
case_files = search_files_for_cases(PatientCaseID, paths)


print(case_files)
print(case_files[PatientCaseID[0]])
print(f'mesh = {case_files[PatientCaseID[0]]["mesh_loader"]}')
print(f'nifti = {case_files[PatientCaseID[0]]["nifti_volume"]}')
print(f'anno = {case_files[PatientCaseID[0]]["anno_loader"]}')
