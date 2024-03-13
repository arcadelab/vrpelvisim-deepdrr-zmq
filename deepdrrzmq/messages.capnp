@0xeaa72c8788903898;

struct Optional(Value) {
    union {
        value @0 :Value;
        none @1 :Void;
    }
}

struct OptionalFloat32 {
    union {
        value @0 :Float32;
        none @1 :Void;
    }
}

struct BoolValue {
    value @0 :Bool;
}

struct Float64Value {
    value @0 :Float64;
}

struct Time {
    millis @0 :Float64;
}

struct Matrix3x3{
    data @0 :List(Float32);
}

struct Matrix4x4 {
    data @0 :List(Float32);
}

struct Mesh {
    vertices @0 :List(Float32);
    faces @1 :List(Int32);
}

struct VolumeMesh {
    mesh @0 :Mesh;
    material @1 :Text;
    density @2 :Float32 = -1;
}

struct MeshLoaderParams {
    meshes @0 :List(VolumeMesh);
    voxelSize @1 :Float32 = 0.1;
}

struct Image {
    data @0 :Data;
}

struct CameraIntrinsics {
    sensorHeight @0 :UInt32 = 1536; # Height of the sensor in pixels
    sensorWidth @1 :UInt32 = 1536; # Width of the sensor in pixels
    pixelSize @2 :Float32 = 0.194; # Size of a pixel in mm
    sourceToDetectorDistance @3 :Float32 = 1020; # Distance from the source to the detector in mm
}

struct CameraProjection {
    intrinsic @0 :CameraIntrinsics; # Camera intrinsics
    extrinsic @1 :Matrix4x4; # Camera extrinsics
}

struct Device {
    camera @0 :CameraProjection; # Camera projection of the device
}

struct NiftiLoaderParams {
    path @0 :Text; # Path to the nifti file on the server
    worldFromAnatomical @1 :Matrix4x4; # Transformation from the world coordinate system to the anatomical coordinate system
    useThresholding @2 :Bool = true; # Segment the materials using thresholding (faster but less accurate)
    useCached @3 :Bool = true; # Use a cached segmentation if available.
    saveCache @4 :Bool = false; # Save the segmentation to a cache file.
    cacheDir @5 :Optional(Text) = (none = void); # Directory to save the cache file to.
    segmentation @6 :Bool = false; # If the file is a segmentation file, then its "materials" correspond to a high density material.
}

struct InstrumentLoaderParams {
    type @0 :Text; # Type of instrument to load, options are: KWire
    worldFromAnatomical @1 :Matrix4x4; # Transformation from the world coordinate system to the anatomical coordinate system
    density @2 :Float32 = 0.1; # Segment the materials using thresholding (faster but less accurate)
}

struct VolumeLoaderParams {
    union {
        nifti @0 :NiftiLoaderParams;
        instrument @1 :InstrumentLoaderParams;
        mesh @2 :MeshLoaderParams;
    }
}
     
struct ProjectorParams {
    volumes @0 :List(VolumeLoaderParams); # List of volumes to project
    priorities @1 :List(UInt32); # List of priorities for each volume
    device @2 :Device; # Device to project from
    step @3 :Float32 = 0.1; # Size of the step along projection ray in voxels. Defaults to 0.1.
    mode @4 :Text = "linear"; # Interpolation mode for the kernel. Defaults to "linear".
    spectrum @5 :Text = "90KV_AL40"; # Spectrum array or name of spectrum to use for projection. Options are `'60KV_AL35'`, `'90KV_AL40'`, and `'120KV_AL43'`.
    scatterNum @6 :UInt32 = 0; # the number of photons to sue in the scatter simulation.  If zero, scatter is not simulated.
    addNoise @7 :Bool = false; # Whether to add Poisson noise. 
    photonCount @8 :UInt32 = 10000; # the average number of photons that hit each pixel. (The expected number of photons that hit each pixel is not uniform over each pixel because the detector is a flat panel.) 
    threads @9 :UInt32 = 8; # Number of threads to use. Defaults to 8.
    maxBlockIndex @10 :UInt32 = 1024; # Maximum GPU block. Defaults to 1024. 
    collectedEnergy @11 :Bool = false; # Whether to return data of "intensity" (energy deposited per photon, [keV]) or "collected energy" (energy deposited on pixel, [keV / mm^2]).
    neglog @12 :Bool = true; # whether to apply negative log transform to intensity images. If True, outputs are in range [0, 1]. Recommended for easy viewing. 
    intensityUpperBound @13 :OptionalFloat32 = (none = void); # Maximum intensity, clipped before neglog, after noise and scatter. A good value is 40 keV / photon. 
    attenuateOutsideVolume @14 :Bool = false; # Whether to attenuate photons outside the volume. 
}

struct StatusResponse {
    code @0 :UInt16; # Status code
    message @1 :Text; # Status message
}

struct ProjectRequest {
    requestId @0 :Text; # Unique request id
    projectorId @1 :Text; # Unique projector id
    cameraProjections @2 :List(CameraProjection); # List of camera projections to project from
    volumesWorldFromAnatomical @3 :List(Matrix4x4); # List of transformations from the world coordinate system to the anatomical coordinate system
}

struct ProjectResponse {
    requestId @0 :Text; # Unique request id
    projectorId @1 :Text; # Unique projector id
    status @2 :StatusResponse; # Status of the request
    images @3 :List(Image); # List of images
}

struct ProjectorParamsResponse {
    projectorId @0 :Text; # Unique projector id
    projectorParams @1 :ProjectorParams; # Projector parameters
}

struct ProjectorParamsRequest {
    projectorId @0 :Text; # Unique projector id
}

struct MeshRequest {
    meshId @0 :Text; # Unique mesh id
}

struct MeshResponse {
    meshId @0 :Text; # Unique mesh id
    status @1 :StatusResponse; # Status of the request
    mesh @2 :Mesh; # Mesh
}

struct AnnoRequest {
    annoId @0 :Text; # Unique annotation id
}

struct AnnoResponse {
    annoId @0 :Text; # Unique annotation id
    status @1 :StatusResponse; # Status of the request
    anno @2 :Anno; # Annotation
}

struct Anno {
    controlPoints @0 :List(ControlPoint); # List of control points
    type @1 :Text; # Type of annotation
}

struct ControlPoint {
    position @0 :Vector3; # Position of the control point
}

struct Vector3 {
    data @0 :List(Float32);
}

struct SyncedTransformUpdate {
    timestamp @0 :Float64; # Timestamp of the transformation matrix
    clientId @1 :Text; # Client id
    transforms @2 :List(Matrix4x4); # Transformation matrices
}

struct ClientHeartbeat {
    clientId @0 :Text;
}

struct SyncedSetting {
    timestamp @0 :Float64; # Timestamp of the setting
    clientId @1 :Text; # Client id
    setting :union {
        float @2 :Float32;
        double @3 :Float64;
        bool @4 :Bool;
        int @5 :Int32;
        long @6 :Int64;
        string @7 :Text;
        arm @8 :CArmSettings;
        uiControl @9 :UIControlSettings; #Need add
    }
}

struct CArmSettings {
    liveCapture @0 :Bool; # Whether to capture live images
}  

struct LogEntry {
    logMonoTime @0 :Float64; # Timestamp of the log message
    topic @1 :Data; # Topic of the log message
    data @2 :Data; # Log message
}

struct LoggerStatus {
    recording @0 :Bool; # Whether the logger is recording
    sessionId @1 :Text; # Session id of the logger
}

# WebUI
struct UIControlSettings  {
    patientMaterial @0 :Int32; # Skin opaque/transparent  
    annotationError @1 :List(Text); # Session id of the logger
    corridorIndicator @2 :Bool; # All corridor indicator bool
    carmIndicator @3 :Bool; # C-arm indicator bool
    webcorridorerrorselect @4 :Bool; # Corridor error web control
    webcorridorselection @5 :Int32 ; # The index of web selection
    flippatient @6 :Bool; # Flip patient bool
    viewIndicatorselfselect @7 :Bool; # View indicator self select bool
    patientCaseID @8 :Text; # Patient case ID
}

struct LogFile {
    id @0 :Text; # Id of the log file
    mtime @1 :Float64; # Last modified time of the log file
}

struct LogList {
    logs @0 :List(LogFile);
}

# Load log (logid, autoplay, start_time, loop)
struct LoadLogRequest {
    logId @0 :Text; # Id of the log file
    autoplay @1 :Bool; # Whether to autoplay the log
    loop @2 :Bool; # Whether to loop the log
}


# Publishes: (don't replay these messages)
# Current state /replayd/state 
# Current time /replayd/time
# Current logid /replayd/logid
struct ReplayerStatus {
    enabled @0 :Bool; # Whether the replayer is enabled
    playing @1 :Bool; # State of the replayer
    time @2 :Float64; # Current time of the replayer
    logId @3 :Text; # Current logid of the replayer
    startTime @4 :Float64; # Start time of the log
    endTime @5 :Float64; # End time of the log
    loop @6 :Bool; # Whether the log is looping
}