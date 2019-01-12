from field_map.abc import BaseMap, Polygon, BaseRobot
import time


class FieldObject(Polygon):
    def __init__(self, *points, expires_in=5):
        self._expires_in = expires_in
        # if it's been a while since the object was last observed, it probably moved.
        # So it's better to delete it from the map.
        
        super().__init__(*points)
        self.expires_at = time.time() + expires_in
    
    def __getattribute__(self, attr): # is this really necessary?
        if attr not in ('is_expired','expires_at','_expires_in'):
            self.expires_at = time.time() + super().__getattribute__('_expires_in') # poke the expiration time
        return super().__getattribute__(attr)
    
    @property
    def is_expired(self):
        print(self.expires_at)
        return time.time()>self.expires_at

class FieldStructure(Polygon):
    def __init__(self, *points):
        super().__init__(*points)


class FieldMap(BaseMap):
    """
    A field map is just a 2d coordinate system. The origin is at bottom-left. The map contains no negative coordinate
    """
    
    def __init__(self, scale=1):
        """
        :param scale: scale of the map, in units per inch
        """
        super().__init__(scale * 27 * 12, scale * 54 * 12)
        # the field is 27 by 54 feet
    
    def __repr__(self):
        return '<Map instance>'

