#!/usr/bin/env python
"""Generic definition of a robot.

Currently subclasses from the iRobotCreate class to allow for
physical control of an iRobot Create base (if the Robot class is
configured to control hardware) but could be subclassed to use other
physical hardware in the future.

A robot has a planner that allows it to select goals and a map to
keep track of other robots, feasible regions to which it can move,
an occupancy grid representation of the world, and role-specific
information (such as a probability layer for the rop robot to keep
track of where robber robots may be).

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
import math
import random
import numpy as np

from shapely.geometry import Point

from cops_and_robots.robo_tools.pose import Pose
from cops_and_robots.robo_tools.iRobot_create import iRobotCreate
from cops_and_robots.robo_tools.planner import GoalPlanner, PathPlanner, Controller
from cops_and_robots.map_tools.map import set_up_fleming
from cops_and_robots.map_tools.map_elements import MapObject


class Robot(iRobotCreate):
    """Class definition for the generic robot object.

    .. image:: img/classes_Robot.png

    Parameters
    ----------
    name : str
        The robot's name.
    pose : array_like, optional
        The robot's initial [x, y, theta] in [m,m,degrees] (defaults to
        [0, 0.5, 0]).
    map_name : str, optional
        The name of the map (defaults to 'fleming').
    role : {'robber','cop'}, optional
        The robot's role in the cops and robbers game.
    status : two-element list of strings, optional
        The robot's initial mission status and movement status. Cops and
        robbers share possible movement statuses, but their mission statuses
         differ entirely. Defaults to ['on the run', 'without a goal'].
    planner_type: {'simple', 'particle', 'MAP'}, optional
        The robot's type of planner.
    consider_others : bool, optional
        Whether this robot generates other robot models (e.g. the primary cop
        will imagine other robots moving around.) Defaults to false.
    control_hardware : bool, optional
        Whether this robot controls physical hardware. Defaults to false.
    **kwargs
        Arguments passed to the ``MapObject`` attribute.

    Attributes
    ----------
    all_robots : dict
        A dictionary of all robot names (as the key) and their respective roles
        (as the value).

    """

    # all_robots = {'Deckard': 'cop',
    #               'Roy': 'robber',
    #               'Leon': 'robber',
    #               'Pris': 'robber',
    #               'Zhora': 'robber',
    #               }

    all_robots = {'Deckard': 'cop',
                  'Roy': 'robber',
                  'Pris': 'robber',
                  'Zhora': 'robber',
                  }

    def __init__(self,
                 name,
                 pose=[0, 0.5, 0],
                 pose_source='python',
                 publish_to_ROS=False,
                 map_name='fleming',
                 role='robber',
                 mission_status='on the run',
                 goal_planner_type='simple',
                 path_planner_type='direct',
                 consider_others=False,
                 **kwargs):

        # Check robot name
        name = name.capitalize()
        if name not in Robot.all_robots:
            raise ValueError('{} is not a robot name from the list '
                             'of acceptable robots: {}'
                             .format(name, Robot.all_robots))

        # Figure out which robots to consider
        if consider_others:
            self.other_robots = Robot.all_robots
            del self.other_robots[name]
        else:
            self.other_robots = {}

        # Object attributes
        self.name = name
        self.pose2D = Pose(pose, pose_source)
        self.role = role
        self.num_goals = None  # number of goals to reach (None for infinite)
        self.mission_status = mission_status
        if not map_name:
            self.map = None
        else:
            self.map = set_up_fleming()
        self.goal_planner = GoalPlanner(self,
                                        publish_to_ROS,
                                        type_=goal_planner_type)
        if publish_to_ROS is False:
            self.path_planner = PathPlanner(self, path_planner_type)
            self.controller = Controller(self)
        self.fusion_engine = None

        # Movement attributes
        self.pose_history = np.array(([0, 0, 0], self.pose2D.pose))

        # Define MapObject
        shape_pts = Point(pose[0:2]).buffer(iRobotCreate.DIAMETER / 2)\
            .exterior.coords
        self.map_obj = MapObject(self.name, shape_pts[:], has_spaces=False,
                                 **kwargs)
        self.update_shape()

        # Add self and others to the map
        if self.role == 'cop':
            self.map.add_cop(self.map_obj)
        else:
            self.map.add_robber(self.map_obj)
        self.make_others()

    def update_shape(self):
        """Update the robot's map_obj.
        """

        # <>TODO: refactor this
        self.map_obj.move_shape((self.pose2D.pose -
                                 self.pose_history[-2:, :]).tolist()[0])

    def make_others(self):
        """Generate robot objects for all other robots.

        Create personal belief (not necessarily true!) of other robots,
        largely regarding their map positions. Their positions are
        known to the 'self' robot, but this function will be expanded
        in the future to include registration between robots: i.e.,
        optional pose and information sharing instead of predetermined
        sharing.
        """

        self.missing_robbers = {}  # all are missing to begin with!
        self.known_cops = {}
        for name, role in self.other_robots.iteritems():

            # Randomly place the other robots
            x = random.uniform(self.map.bounds[0], self.map.bounds[2])
            y = random.uniform(self.map.bounds[1], self.map.bounds[3])
            theta = random.uniform(0, 359)
            pose = [x, y, theta]

            # Add other robots to the map
            if role == 'robber':
                new_robber = robber_module.Robber(name, pose=pose)
                self.map.add_robber(new_robber.map_obj)
                self.missing_robbers[name] = new_robber
            else:
                new_cop = cop_module.Cop(name, pose=pose)
                self.map.add_cop(new_cop.map_obj)
                self.known_cops[name] = new_cop

    def stop_all_movement(self):
        self.goal_planner.goal_status = 'done'
        try:
            self.path_planner.planner_status = 'not planning'
            self.controller.controller_status = 'waiting'
        except:
            logging.info('No planner or controller found')
        logging.warn('{} has stopped'.format(self.name))
        self.mission_status = 'stopped'

    def update(self, i=0):
        """Update all primary functionality of the robot.

        This includes planning and movement for both cops and robbers,
        as well as sensing and map animations for cops.

        Parameters
        ----------
        i : int, optional
            The current animation frame. Default is 0 for non-animated robots.

        Returns
        -------
        tuple or None
            `None` if the robot does not generate an animation packet, or a
            tuple of all animation parameters otherwise.
        """
        if self.mission_status is not 'stopped':
            # Update statuses and planners
            self.update_mission_status()
            self.goal_planner.update()
            if self.goal_planner.publish_to_ROS is False:
                self.path_planner.update()
                self.controller.update()

            # Add to the pose history, update the map
            self.pose_history = np.vstack((self.pose_history, self.pose2D.pose[:]))
            self.update_shape()

            # Update sensor and fusion information, if a cop
            if self.role == 'cop':
                # Try to visually spot a robber
                for missing_robber in self.missing_robbers.values():
                    self.sensors['camera'].detect_robber(missing_robber)

                # Update probability model
                self.fusion_engine.update(self.pose2D.pose, self.sensors,
                                          self.missing_robbers)
            # Export the next animation stream
            if self.role == 'cop' and self.show_animation:
                packet = {}
                if not self.map.combined_only:
                    for i, robber_name in enumerate(self.missing_robbers):
                        packet[robber_name] = \
                            self._form_animation_packet(robber_name)
                packet['combined'] = self._form_animation_packet('combined')
                return self.stream.send(packet)

    def _form_animation_packet(self, robber_name):
        """Turn all important animation data into a tuple.

        Parameters
        ----------
        robber_name : str
            The name of the robber (or 'combined') associated with this packet.

        Returns
        -------
        tuple
            All important animation parameters.

        """
        # Cop-related values
        cop_shape = self.map_obj.shape
        if len(self.pose_history) < self.goal_planner.stuck_buffer:
            cop_path = np.hsplit(self.pose_history[:, 0:2], 2)
        else:
            cop_path = np.hsplit(self.pose_history[-self.goal_planner.stuck_buffer:, 0:2],
                                 2)

        camera_shape = self.sensors['camera'].viewcone.shape

        # Robber-related values
        particles = self.fusion_engine.filters[robber_name].particles
        if robber_name == 'combined':
            robber_shape = {name: robot.map_obj.shape for name, robot
                            in self.missing_robbers.iteritems()}
        else:
            robber_shape = self.missing_robbers[robber_name].map_obj.shape

        # Form and return packet to be sent
        packet = (cop_shape, cop_path, camera_shape, robber_shape, particles,)
        return packet

# Import statements left to the bottom because of subclass circular dependency
import cops_and_robots.robo_tools.cop as cop_module
import cops_and_robots.robo_tools.robber as robber_module
