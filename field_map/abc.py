import shapely.geometry
import time
import abc


class Singleton(type):
    def __call__(cls, *args, **kwargs):
        if not hasattr(cls, '_obj'):
            obj = cls.__new__(cls)
            obj.__init__(*args, **kwargs)
            cls._instance = obj
        return cls._instance


class BaseMap(metaclass=Singleton):
    def __init__(self, w, l):
        self.width = w
        self.length = l
        self._objects = {}
    
    def add_object(self, obj, name=None, ):
        """
        Add a object to
        :param obj: a Polygon
        :param name: optional. The name of the object. This can be used to retrieve the object later.
        :return: None
        """
        assert isinstance(obj, Polygon) or isinstance(obj, BaseRobot), 'The object must be a polygon or a robot'
        
        if name is None:
            self._objects[id(obj)] = obj
        else:
            assert name not in self._objects
            self._objects[name] = obj
    
    def update_object(self, name, obj):
        assert isinstance(name,
                          str) and name in self._objects, 'Update can only be performed on a named existing object'
        
        self._objects[name] = obj
    
    def remove_object(self, obj):
        """
        :param obj: the name of object or the object itself.
        :return:
        """
        if isinstance(obj, str):
            del self._objects[obj]
        else:
            del self._objects[id(obj)]
    
    def __getitem__(self, item):
        if isinstance(item, str):
            return self._objects[item]
        else:
            return self._objects[id(item)]
    
    def __iter__(self):
        return iter(self._objects.values())
    
    def __repr__(self):
        return f'<BaseMap instance>'
    
    def intersect(self, other):
        """
        :param other: a polygon
        :return: True if the polygon intersects with anything in the map
        """
        for obj in self:
            if obj.is_expired:
                self.remove_object(obj)
                print('Removed object %s: expired' % obj)
                continue
            
            if obj.intersects(other):
                return True
        
        return False


class Polygon(shapely.geometry.Polygon):
    def __init__(self, *points):
        super().__init__(points)  # it wouldn't make sense to have a hole in a polygon for our purpose
        self.points = tuple(map(tuple, points))  # so it's hashable
    
    def __repr__(self):
        return f'<{self}>'
    
    def __hash__(self):
        return hash(self.points)
    
    def __iter__(self):
        return iter(self.points)
    
    @property
    def is_expired(self):
        return False


class BaseRobot(metaclass=Singleton):
    """
    Robot represents the current robot. For enemy robots, use a polygon
    """
    
    def __init__(self, width, length):
        self.width = width
        self.length = length
        self._polygon = Polygon((0, 0), (width, 0), (width, length), (0, length))
        self.is_expired = False
    
    def __getattr__(self, item):
        try:
            return getattr(self._polygon, item)
        except AttributeError:
            e = AttributeError('Robot has no attribute %s' % item)
            e.__suppress_context__ = True
            raise e
    
    def move_forward(self, distance):
        raise NotImplementedError
    
    def move_backward(self, distance):
        raise NotImplementedError
    
    def turn(self,distance):
        raise NotImplementedError
    
