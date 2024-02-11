from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from deepdrr import geo
from deepdrr.device import Device

class SimpleDevice(Device):
    """
    Simple DeepDRR device which only uses the camera intrinsics and the world from device transform.
    """
    sensor_height: int
    sensor_width: int
    pixel_size: float

    camera_intrinsics: geo.CameraIntrinsicTransform
    source_to_detector_distance: float
    world_from_device: geo.FrameTransform

    def __init__(self, sensor_height: int, sensor_width: int, pixel_size: float, source_to_detector_distance: float, world_from_device: geo.FrameTransform):
        """
        :param sensor_height: height of the sensor in pixels
        :param sensor_width: width of the sensor in pixels
        :param pixel_size: size of a pixel in       mm
        :param source_to_detector_distance: distance from the source to the detector in mm
        :param world_from_device: transform from the device to the world
        """
        self.sensor_height = sensor_height
        self.sensor_width = sensor_width
        self.pixel_size = pixel_size
        self.source_to_detector_distance = source_to_detector_distance
        self.world_from_device = world_from_device
        self.camera_intrinsics = geo.CameraIntrinsicTransform.from_sizes(
            sensor_size=(sensor_width, sensor_height),
            pixel_size=pixel_size,
            source_to_detector_distance=self.source_to_detector_distance,
        )

    @property
    def device_from_camera3d(self) -> geo.FrameTransform:
        return geo.frame_transform(None)

    @property
    def principle_ray(self) -> geo.Vector3D:
        return geo.v(0, 0, 1)
