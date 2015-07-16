#!/usr/bin/env python
"""Defines physical and non-physical objects used in the map environment.

``map_obj`` extends Shapely's geometry objects (generally polygons) to
be used in a robotics environmnt. Map objects can be physical,
representing walls, or non-physical, representing camera viewcones.

The visibility of an object can be toggled, and each object can have
*spaces* which define areas around the object. For example, a
rectangular wall has four intrinsic exterior spaces: front, back, left and
right. These are named spaces, but arbitrary shapes can have arbitrary numbered
spaces (such as a triangle with three numbered spaces).

"""
__author__ = "Nick Sweet"
__copyright__ = "Copyright 2015, Cohrint"
__credits__ = ["Nick Sweet", "Nisar Ahmed"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Nick Sweet"
__email__ = "nick.sweet@colorado.edu"
__status__ = "Development"

import logging

import matplotlib.pyplot as plt
from matplotlib.colors import cnames
from shapely.geometry import box, Polygon, LineString
from shapely.affinity import rotate
from descartes.patch import PolygonPatch

from cops_and_robots.fusion.softmax import (binary_range_model,
                                            binary_intrinsic_space_model,
                                            range_model,
                                            intrinsic_space_model)


class MapElement(object):
    """Generate an element based on a geometric shape, plus spatial relations.

    Spaces demarcate spatial relationships around elements.

    .. image:: img/classes_Map_Element.png

    Note
    ----
        If only one xy pair is given as shape_pts, MapElement will assume
        the user wants to create a box with those two values as length
        and width, respectively.

        Shapes are created such that the centroid angle (the direction
        the element is facing) is 0. To change this, use ``move_shape``.

    Parameters
    ----------
    name : str
        The map element's name.
    shape_pts : array_like
        A list of xy pairs as [(x_i,y_i)] in [m,m] in the global (map)
        coordinate frame.
    pose : array_like, optional
        The map element's initial [x, y, theta] in [m,m,degrees] (defaults to
        [0, 0, 0]).
    visible : bool, optional
        Whether the element will be visibile to the human.
        Default True
    blocks_camera : bool, optional
        Whether the element will interfere with the camera.
        Default True
    centroid_at_origin : bool, optional
        Whether the element's centroid is placed at the map origin (as opposed
        to placing the element's lower-left corner at the map origin). Default
        is `True`.
    color_str : str, optional
        The color string for the element. Default is `'darkblue'`.

    """
    def __init__(self, name, shape_pts, pose=[0, 0, 0], visible=True,
                 show_name=False, has_spaces=False, plot_spaces=False,
                 blocks_camera=True, centroid_at_origin=True,
                 space_resolution=0.1, color_str='darkblue', alpha=0.5):
        # Define basic MapElement properties
        self.has_spaces = has_spaces
        self.plot_spaces = plot_spaces
        self.name = name
        self.visible = visible
        self.blocks_camera = blocks_camera
        self.space_resolution = space_resolution
        self.color = cnames[color_str]
        self.pose = pose
        self.alpha = alpha

        # If shape has only length and width, convert to point-based poly
        if len(shape_pts) == 2:
            shape_pts = [list(b) for b in
                         box(0, 0, shape_pts[0], shape_pts[1]).exterior.coords]

        # Build the map element's polygon (shape)
        if centroid_at_origin:
            shape = Polygon(shape_pts)
            x, y = shape.centroid.x, shape.centroid.y
            shape_pts = [(p[0] - x, p[1] - y) for p in shape_pts]
        self.shape = Polygon(shape_pts)

        # Store polygon shape
        self.base_shape = self.shape

        # Place the shape at the correct pose
        self.move_relative(pose)

    def move_absolute(self, pose):
        """Moves shape to new pose"""
        # Rotate about center
        pts = self.base_shape.exterior.coords
        center = self.base_shape.centroid
        lines = []
        for pt in pts:
            line = LineString([center, pt])
            lines.append(rotate(line, pose[2], origin=center))
        pts = []
        for line in lines:
            pts.append(line.coords[1])
        rotated_shape = Polygon(pts)

        # Move shape to new pose
        self.pose = pose
        shape_pts = [(p[0] + pose[0], p[1] + pose[1])
                     for p in rotated_shape.exterior.coords]
        self.shape = Polygon(shape_pts)

        # Redefine sides, points and and spaces
        self.points = self.shape.exterior.coords
        self.sides = []
        self.spaces = []
        self.spaces_by_label = {}
        if self.has_spaces:
            self.define_spaces()

    def move_relative(self, pose, rotation_pt=None):
        """Translate and rotate the shape.

        The rotation is assumed to be about the element's centroid
        unless a rotation point is specified.

        Parameters
        ----------
        pose : array_like, optional
            The map element's initial [x, y, theta] in [m,m,degrees].
        rotation_pt : array_like
            The rotation point as [x,y] in [m,m]. Defaults to the centroid.

        """
        if rotation_pt:
            rotation_point = rotation_pt
        else:
            rotation_point = self.shape.centroid

        # Rotate the polygon
        self.rotate_poly(pose[2], rotation_point)

        # Translate the polygon
        self.pose = pose
        shape_pts = [(p[0] + pose[0], p[1] + pose[1])
                     for p in self.shape.exterior.coords]
        self.shape = Polygon(shape_pts)

        # Redefine sides, points and and spaces
        self.points = self.shape.exterior.coords
        self.sides = []
        self.spaces = []
        self.spaces_by_label = {}
        if self.has_spaces:
            self.define_spaces()

    def rotate_poly(self, angle, rotation_point):
        """Rotate the shape about a rotation point.

        Parameters
        ----------
        angle : float
            The angle to be rotated in degrees.
        rotation_pt : array_like
            The rotation point as [x,y] in [m,m].

        """
        pts = self.shape.exterior.coords
        lines = []
        for pt in pts:
            line = LineString([rotation_point, pt])
            lines.append(rotate(line, angle, origin=rotation_point))

        pts = []
        for line in lines:
            pts.append(line.coords[1])

        self.shape = Polygon(pts)

    def get_patch(self, **kwargs):
        """Returns a polygon patch of the object for plotting purposes"""
        patch = PolygonPatch(self.shape, facecolor=self.color,
                             alpha=self.alpha, zorder=2, **kwargs)
        return patch

    def plot(self, ax=None, alpha=0.5, plot_spaces=False, **kwargs):
        """DO NOT USE
        Plot the map_element as a polygon patch.

        plot_spaces : bool, optional
            Plot the map element's spaces if true. Defaults to `False`.
        ax : axes handle, optional
            The axes to be used for plotting. Defaults to current axes.
        alpha: float, optional
            Transparency of all elements of the shape. Default is 0.5.
        **kwargs
            Arguments passed to ``PolygonPatch``.

        Note
        ----
            The spaces can be plotted without the shape if the shape's
            ``visible`` attribute is False, but ``plot_spaces`` is True.

            DO NOT USE, use get_patch and plot using the shapelayer
        """

        if not ax:
            ax = plt.gca()

        patch = PolygonPatch(self.shape, facecolor=self.color,
                             alpha=alpha, zorder=2, **kwargs)
        ax.add_patch(patch)

        logging.warn('You should use get_patch instead of plot')
        return patch

    def __str___(self):
        str_ = "{} is located at ({},{}), pointing at {}}"
        return str_.format(self.name,
                           self.centroid['x'],
                           self.centroid['y'],
                           self.centroid['theta'],
                           )


class MapObject(MapElement):
    """Physical object in the map.

    long description of MapObject
    """

    def __init__(self, name, shape_pts, color_str='darkseagreen', alpha=0.9,
                 visible=True, blocks_camera=True, has_spaces=True,
                 plot_spaces=False, **kwargs):
        super(MapObject, self).__init__(name, shape_pts,
                                        color_str=color_str,
                                        visible=visible,
                                        blocks_camera=blocks_camera,
                                        has_spaces=has_spaces,
                                        plot_spaces=plot_spaces,
                                        alpha=alpha,
                                        **kwargs
                                        )
        if self.has_spaces:
            self.define_spaces()
            self.plot_spaces = plot_spaces
        else:
            plot_spaces = False

    def define_spaces(self):
            """Create a multimodal softmax model of spatial relationships.

            Defaults to: 'Front', 'Back', 'Left', and 'Right'.
            """
            # self.spaces = intrinsic_space_model(self.shape)
            self.spaces = binary_intrinsic_space_model(self.shape)


class MapArea(MapElement):
    """short description of MapArea

    long description of MapArea

    """

    def __init__(self, name, shape_pts, color_str='blanchedalmond', alpha=0.9,
                 visible=False, blocks_camera=False, has_spaces=True,
                 plot_spaces=False, **kwargs):
        super(MapArea, self).__init__(name, shape_pts,
                                      color_str=color_str,
                                      visible=visible,
                                      blocks_camera=blocks_camera,
                                      has_spaces=has_spaces,
                                      plot_spaces=plot_spaces,
                                      alpha=alpha,
                                      **kwargs
                                      )
        if self.has_spaces:
            self.define_spaces()
            self.plot_spaces = plot_spaces
        else:
            self.plot_spaces = False

    def define_spaces(self):
        """Create a multimodal softmax model of spatial relationships.

        Defaults to: 'Inside', 'Near', and 'Outside'.
        """
        self.spaces = range_model(self.shape)
        # self.spaces = binary_range_model(self.shape)

    # Handle with Information
    # def plot(self, ax=None, alpha=0.2, **kwargs):
    #     super(MapArea, self).plot(ax=ax, alpha=alpha, **kwargs)
    #     if self.show_name:
    #         if not ax:
    #             ax = plt.gca()
    #         ax.annotate(self.name, self.pose[:2])
