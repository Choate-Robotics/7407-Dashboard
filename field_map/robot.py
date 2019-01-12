from field_map.abc import BaseRobot

class Robot(BaseRobot):
    """
    Represents an actual robot on the field. Communicates with roboRIO via netweorktable
    """

class SimulatedRobot(BaseRobot):
    """
    Represents a simulated robot.
    """
