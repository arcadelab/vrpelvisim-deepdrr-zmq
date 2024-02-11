
from typing import Dict, Optional
from deepdrr.instruments import Instrument
from deepdrr import geo


class KWire450mm(Instrument):
    """
    An instrument representing a 450mm K-wire.
    """
    def __init__(
        self,
        density: float = 0.1,
        world_from_anatomical: Optional[geo.FrameTransform] = None,
        densities: Dict[str, float] = {},
    ):
        """
        :param density: density of the K-wire in g/cm^3
        :param world_from_anatomical: transform from the anatomical to the world
        :param densities: densities of the anatomical structures in g/cm^3
        """
        super().__init__(density, world_from_anatomical, densities)

