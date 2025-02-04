import os
import time
import numpy as np

import pybullet as p
from surrol.tasks.psm_env import PsmsEnv, goal_distance
from surrol.utils.pybullet_utils import (
    get_link_pose,
    reset_camera, 
    wrap_angle
)
from surrol.tasks.ecm_env import EcmEnv, goal_distance

from surrol.robots.ecm import RENDER_HEIGHT, RENDER_WIDTH, FoV
from surrol.const import ASSET_DIR_PATH
from surrol.robots.ecm import Ecm


class BiPegTransfer(PsmsEnv):
    POSE_BOARD = ((0.55, 0, 0.6861), (0, 0, 0))
    WORKSPACE_LIMITS1 = ((0.50, 0.60), (-0., 0.05), (0.686, 0.745))
    WORKSPACE_LIMITS2 = ((0.50, 0.60), (-0.05, 0.), (0.686, 0.745))
    SCALING = 5.
    QPOS_ECM = (0, 0.6, 0.04, 0)
    ACTION_ECM_SIZE=3
    #for haptic device demo  
    haptic=True
    def __init__(self, render_mode=None, cid = -1):
        super(BiPegTransfer, self).__init__(render_mode, cid)
        self._view_matrix = p.computeViewMatrixFromYawPitchRoll(
            cameraTargetPosition=(-0.05 * self.SCALING, 0, 0.375 * self.SCALING),
            distance=1.81 * self.SCALING,
            yaw=90,
            pitch=-30,
            roll=0,
            upAxisIndex=2
        )

    def _env_setup(self):
        super(BiPegTransfer, self)._env_setup()
        self.has_object = True

        # camera
        if self._render_mode == 'human':
            reset_camera(yaw=90.0, pitch=-30.0, dist=0.82 * self.SCALING,
                         target=(-0.05 * self.SCALING, 0, 0.36 * self.SCALING))
        self.ecm = Ecm((0.15, 0.0, 0.8524), #p.getQuaternionFromEuler((0, 30 / 180 * np.pi, 0)),
                       scaling=self.SCALING)
        self.ecm.reset_joint(self.QPOS_ECM)
        # p.setPhysicsEngineParameter(enableFileCaching=0,numSolverIterations=10,numSubSteps=128,contactBreakingThreshold=2)


        # robot
        workspace_limits = self.workspace_limits1
        pos = (workspace_limits[0][0],
               workspace_limits[1][1],
               workspace_limits[2][1])
        orn = (0.5, 0.5, -0.5, -0.5)
        joint_positions = self.psm1.inverse_kinematics((pos, orn), self.psm1.EEF_LINK_INDEX)
        self.psm1.reset_joint(joint_positions)
        workspace_limits = self.workspace_limits2
        pos = (workspace_limits[0][0],
               workspace_limits[1][0],
               workspace_limits[2][1])
        joint_positions = self.psm2.inverse_kinematics((pos, orn), self.psm2.EEF_LINK_INDEX)
        self.psm2.reset_joint(joint_positions)
        self.block_gripper = False

        # peg board
        obj_id = p.loadURDF(os.path.join(ASSET_DIR_PATH, 'peg_board/peg_board.urdf'),
                            np.array(self.POSE_BOARD[0]) * self.SCALING,
                            p.getQuaternionFromEuler(self.POSE_BOARD[1]),
                            globalScaling=self.SCALING)
        self.obj_ids['fixed'].append(obj_id)  # 1
        self._pegs = np.arange(12)
        np.random.shuffle(self._pegs[:6])
        np.random.shuffle(self._pegs[6: 12])

        # blocks
        num_blocks = 6
        for i in self._pegs[6: 6 + num_blocks]:
            pos, orn = get_link_pose(self.obj_ids['fixed'][1], i)
            yaw = (np.random.rand() - 0.5) * np.deg2rad(60)
            obj_id = p.loadURDF(os.path.join(ASSET_DIR_PATH, 'block/block.urdf'),
                                np.array(pos) + np.array([0, 0, 0.03]),
                                p.getQuaternionFromEuler((0, 0, yaw)),
                                useFixedBase=False,
                                globalScaling=self.SCALING)
            self.obj_ids['rigid'].append(obj_id)
        self._blocks = np.array(self.obj_ids['rigid'][-num_blocks:])
        np.random.shuffle(self._blocks)
        for obj_id in self._blocks[:1]:
            # change color to red
            p.changeVisualShape(obj_id, -1, rgbaColor=(255 / 255, 69 / 255, 58 / 255, 1))
            pos, _ = p.getBasePositionAndOrientation(obj_id)
            # p.resetBasePositionAndOrientation(obj_id, pos, (0, 0, 0, 1))  # reduce difficulty
        self.obj_id, self.obj_link1, self.obj_link2 = self._blocks[0], 1, 2

    # def _set_action(self, action: np.ndarray):
    #     # simplified to a hand and drop by performing the first three steps
    #     obs = self._get_obs()
    #     if not self._waypoints_done[3]:  # 1: approach, 2: pick, 3: lift
    #         action = self.get_oracle_action(obs)
    #     super(BiPegTransfer, self)._set_action(action)

    def _is_success(self, achieved_goal, desired_goal):
        """ Indicates whether or not the achieved goal successfully achieved the desired goal.
        """
        # TODO: may need to tune parameters
        return np.logical_and(
            goal_distance(achieved_goal[..., :2], desired_goal[..., :2]) < 5e-3 * self.SCALING,
            np.abs(achieved_goal[..., -1] - desired_goal[..., -1]) < 4e-3 * self.SCALING
        ).astype(np.float32)

    def _sample_goal(self) -> np.ndarray:
        """ Samples a new goal and returns it.
        """
        goal = np.array(get_link_pose(self.obj_ids['fixed'][1], self._pegs[0])[0])
        return goal.copy()

    def _sample_goal_callback(self):
        """ Define waypoints
        """
        super()._sample_goal_callback()
        self._waypoints = []  # eleven waypoints
        pos_obj1, orn_obj1 = get_link_pose(self.obj_id, self.obj_link1)
        pos_obj2, orn_obj2 = get_link_pose(self.obj_id, self.obj_link2)
        orn1 = p.getEulerFromQuaternion(orn_obj1)
        orn2 = p.getEulerFromQuaternion(orn_obj2)
        orn_eef1 = p.getEulerFromQuaternion(get_link_pose(self.psm1.body, self.psm1.EEF_LINK_INDEX)[1])
        orn_eef2 = p.getEulerFromQuaternion(get_link_pose(self.psm2.body, self.psm2.EEF_LINK_INDEX)[1])
        yaw1 = orn1[2] if abs(wrap_angle(orn1[2] - orn_eef1[2])) < abs(wrap_angle(orn1[2] + np.pi - orn_eef1[2])) \
            else wrap_angle(orn1[2] + np.pi)  # minimize the delta yaw
        yaw2 = orn2[2] if abs(wrap_angle(orn2[2] - orn_eef2[2])) < abs(wrap_angle(orn2[2] + np.pi - orn_eef2[2])) \
            else wrap_angle(orn2[2] + np.pi)  # minimize the delta yaw

        # the corresponding peg position
        # pos_peg = get_link_pose(self.obj_ids['fixed'][1], self.obj_id - np.min(self._blocks) + 6)[0]  # 6 pegs
        pos_peg = get_link_pose(self.obj_ids['fixed'][1],
                                self._pegs[self.obj_id - np.min(self._blocks) + 6])[0]  # 6 pegs

        pos_mid1 = [pos_obj1[0],
                    0. + pos_obj1[1] - pos_peg[1], pos_obj1[2] + 0.043 * self.SCALING]  # consider offset
        pos_mid2 = [pos_obj2[0],
                    0. + pos_obj2[1] - pos_peg[1], pos_obj2[2] + 0.043 * self.SCALING]  # consider offset

        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
                                         pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
                                         pos_obj2[0], pos_obj2[1]-0.005,
                                         pos_mid2[2], yaw2, 0.5]))  # above object
        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
                                         pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
                                         pos_obj2[0], pos_obj2[1]-0.005,
                                         pos_obj2[2] + (0.003 + 0.0102) * self.SCALING, yaw2, 0.5]))  # approach
        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
                                         pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
                                         pos_obj2[0], pos_obj2[1]-0.005,
                                         pos_obj2[2] + (0.003 + 0.0102) * self.SCALING, yaw2, -0.5]))  # psm2 grasp
        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
                                         pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
                                         pos_obj2[0], pos_obj2[1]-0.005,
                                         pos_mid2[2], yaw2, -0.5]))  # lift up

        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # move to middle

        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, 0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # psm1 pre grasp

        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # psm1 grasp

        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2], yaw2, 0.5]))  # psm2 release
        self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
                                         yaw2, 0.5]))  # psm2 lift up

        pos_place = [self.goal[0] + pos_obj1[0] - pos_peg[0],
                     self.goal[1] + pos_obj1[1] - pos_peg[1], pos_mid1[2]]  # consider offset
        self._waypoints.append(np.array([pos_place[0]-0.02, pos_place[1]-0.0135, pos_place[2], yaw1, -0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
                                         yaw2, 0.5]))  # above goal
        self._waypoints.append(np.array([pos_place[0]-0.02, pos_place[1]-0.0135, pos_place[2], yaw1, 0.5,
                                         pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
                                         yaw2, 0.5]))  # above goal
        self._waypoints_done = [False] * len(self._waypoints)

    def _meet_contact_constraint_requirement(self):
        # add a contact constraint to the grasped block to make it stable
        if self.haptic is True:
            # print(f'meet due to hardcoe')
            return True
        else:
            pose = get_link_pose(self.obj_id, -1)
            return pose[0][2] > self.goal[2] + 0.01 * self.SCALING  # reduce difficulty

    def get_oracle_action(self, obs) -> np.ndarray:
        """
        Define a human expert strategy
        """
        # eleven waypoints executed in sequential order
        action = np.zeros(10)
        for i, waypoint in enumerate(self._waypoints):
            if self._waypoints_done[i]:
                continue
            delta_pos1 = (waypoint[0: 3] - obs['observation'][0: 3]) / 0.01 / self.SCALING
            delta_yaw1 = (waypoint[3] - obs['observation'][5]).clip(-1, 1)
            delta_pos2 = (waypoint[5: 8] - obs['observation'][7: 10]) / 0.01 / self.SCALING
            delta_yaw2 = (waypoint[8] - obs['observation'][12]).clip(-1, 1)
            if np.abs(delta_pos1).max() > 1:
                delta_pos1 /= np.abs(delta_pos1).max()
            if np.abs(delta_pos2).max() > 1:
                delta_pos2 /= np.abs(delta_pos2).max()
            scale_factor = 0.7
            delta_pos1 *= scale_factor
            delta_pos2 *= scale_factor
            action = np.array([delta_pos1[0], delta_pos1[1], delta_pos1[2], delta_yaw1, waypoint[4],
                               delta_pos2[0], delta_pos2[1], delta_pos2[2], delta_yaw2, waypoint[9]])
            # print(' dis: {:.4f}, {:.4f}, {:.4f}, {:.4f}'.format(
            #     np.linalg.norm(delta_pos1), np.abs(delta_yaw1),
            #     np.linalg.norm(delta_pos2), np.abs(delta_yaw2)))
            if np.linalg.norm(delta_pos1) * 0.01 / scale_factor < 2e-3 and np.abs(delta_yaw1) < np.deg2rad(2.) \
                    and np.linalg.norm(delta_pos2) * 0.01 / scale_factor < 2e-3 and np.abs(delta_yaw2) < np.deg2rad(2.):
                self._waypoints_done[i] = True
            break

        return action
    def _set_action_ecm(self, action):
        action *= 0.01 * self.SCALING
        pose_rcm = self.ecm.get_current_position()
        pose_rcm[:3, 3] += action
        pos, _ = self.ecm.pose_rcm2world(pose_rcm, 'tuple')
        joint_positions = self.ecm.inverse_kinematics((pos, None), self.ecm.EEF_LINK_INDEX)  # do not consider orn
        self.ecm.move_joint(joint_positions[:self.ecm.DoF])
    def _reset_ecm_pos(self):
        self.ecm.reset_joint(self.QPOS_ECM)
# import math
# from haptic_src.test import initTouch_right, closeTouch_right, getDeviceAction_right, startScheduler, stopScheduler
# from haptic_src.test import initTouch_left, closeTouch_left, getDeviceAction_left

# class BiPegTransferHaptic(PsmsEnv):
#     POSE_BOARD = ((0.55, 0, 0.6861), (0, 0, 0))
#     WORKSPACE_LIMITS1 = ((0.50, 0.60), (-0., 0.05), (0.686, 0.745))
#     WORKSPACE_LIMITS2 = ((0.50, 0.60), (-0.05, 0.), (0.686, 0.745))
#     SCALING = 5.
#     QPOS_ECM = (0, 0.6, 0.04, 0)
#     ACTION_ECM_SIZE=3
#     #for haptic device demo  
#     haptic=True
#     def __init__(self, render_mode=None, cid = -1):
#         super(BiPegTransferHaptic, self).__init__(render_mode, cid)
#         self._view_matrix = p.computeViewMatrixFromYawPitchRoll(
#             cameraTargetPosition=(-0.05 * self.SCALING, 0, 0.375 * self.SCALING),
#             distance=1.81 * self.SCALING,
#             yaw=90,
#             pitch=-30,
#             roll=0,
#             upAxisIndex=2
#         )
#         """===initialize haptic==="""
#         initTouch_right()
#         initTouch_left()
#         startScheduler()
#         """======================="""

#     def _env_setup(self):
#         super(BiPegTransferHaptic, self)._env_setup()
#         self.has_object = True

#         # camera
#         if self._render_mode == 'human':
#             # reset_camera(yaw=90.0, pitch=-36.8, dist=4.3,
#             #              target=(-0.25, -0.01, 1.48))
#             reset_camera(yaw=89.60, pitch=-56, dist=5.98,
#                          target=(-0.13, 0.03,-0.94))
#         self.ecm = Ecm((0.15, 0.0, 0.8524), #p.getQuaternionFromEuler((0, 30 / 180 * np.pi, 0)),
#                        scaling=self.SCALING)
#         self.ecm.reset_joint(self.QPOS_ECM)
#         # p.setPhysicsEngineParameter(enableFileCaching=0,numSolverIterations=10,numSubSteps=128,contactBreakingThreshold=2)


#         # robot
#         workspace_limits = self.workspace_limits1
#         pos = (workspace_limits[0][0],
#                workspace_limits[1][1],
#                workspace_limits[2][1])
#         orn = (0.5, 0.5, -0.5, -0.5)
#         joint_positions = self.psm1.inverse_kinematics((pos, orn), self.psm1.EEF_LINK_INDEX)
#         self.psm1.reset_joint(joint_positions)
#         workspace_limits = self.workspace_limits2
#         pos = (workspace_limits[0][0],
#                workspace_limits[1][0],
#                workspace_limits[2][1])
#         joint_positions = self.psm2.inverse_kinematics((pos, orn), self.psm2.EEF_LINK_INDEX)
#         self.psm2.reset_joint(joint_positions)
#         self.block_gripper = False

#         # peg board
#         obj_id = p.loadURDF(os.path.join(ASSET_DIR_PATH, 'peg_board/peg_board.urdf'),
#                             np.array(self.POSE_BOARD[0]) * self.SCALING,
#                             p.getQuaternionFromEuler(self.POSE_BOARD[1]),
#                             globalScaling=self.SCALING)
#         self.obj_ids['fixed'].append(obj_id)  # 1
#         self._pegs = np.arange(12)
#         # np.random.shuffle(self._pegs[:6])
#         # np.random.shuffle(self._pegs[6: 12])

#         # blocks
#         num_blocks = 6
#         for i in self._pegs[1: 1+num_blocks]:
#             pos, orn = get_link_pose(self.obj_ids['fixed'][1], i)
#             yaw =  np.deg2rad(60)
#             obj_id = p.loadURDF(os.path.join(ASSET_DIR_PATH, 'block/block.urdf'),
#                                 np.array(pos) + np.array([0, 0, 0.03]),
#                                 p.getQuaternionFromEuler((0, 0, yaw)),
#                                 useFixedBase=False,
#                                 globalScaling=self.SCALING)
#             self.obj_ids['rigid'].append(obj_id)
#         self._blocks = np.array(self.obj_ids['rigid'][-num_blocks:])
#         # np.random.shuffle(self._blocks)
#         for obj_id in self._blocks[:1]:
#             # change color to red
#             p.changeVisualShape(obj_id, -1, rgbaColor=(255 / 255, 69 / 255, 58 / 255, 1))
#             pos, _ = p.getBasePositionAndOrientation(obj_id)
#             # p.resetBasePositionAndOrientation(obj_id, pos, (0, 0, 0, 1))  # reduce difficulty
#         self.obj_id, self.obj_link1, self.obj_link2 = self._blocks[0], 1, 2

#     # def _set_action(self, action: np.ndarray):
#     #     # simplified to a hand and drop by performing the first three steps
#     #     obs = self._get_obs()
#     #     if not self._waypoints_done[3]:  # 1: approach, 2: pick, 3: lift
#     #         action = self.get_oracle_action(obs)
#     #     super(BiPegTransfer, self)._set_action(action)

#     def _is_success(self, achieved_goal, desired_goal):
#         """ Indicates whether or not the achieved goal successfully achieved the desired goal.
#         """
#         # TODO: may need to tune parameters
#         return np.logical_and(
#             goal_distance(achieved_goal[..., :2], desired_goal[..., :2]) < 5e-3 * self.SCALING,
#             np.abs(achieved_goal[..., -1] - desired_goal[..., -1]) < 4e-3 * self.SCALING
#         ).astype(np.float32)

#     def _sample_goal(self) -> np.ndarray:
#         """ Samples a new goal and returns it.
#         """
#         goal = np.array(get_link_pose(self.obj_ids['fixed'][1], self._pegs[8])[0])
#         return goal.copy()
#     def _sample_goal_callback(self):
#         """ Define waypoints
#         """
#         super()._sample_goal_callback()
#         self._waypoints = []  # eleven waypoints
#         pos_obj1, orn_obj1 = get_link_pose(self.obj_id, self.obj_link1)
#         pos_obj2, orn_obj2 = get_link_pose(self.obj_id, self.obj_link2)
#         orn1 = p.getEulerFromQuaternion(orn_obj1)
#         orn2 = p.getEulerFromQuaternion(orn_obj2)
#         orn_eef1 = p.getEulerFromQuaternion(get_link_pose(self.psm1.body, self.psm1.EEF_LINK_INDEX)[1])
#         orn_eef2 = p.getEulerFromQuaternion(get_link_pose(self.psm2.body, self.psm2.EEF_LINK_INDEX)[1])
#         yaw1 = orn1[2] if abs(wrap_angle(orn1[2] - orn_eef1[2])) < abs(wrap_angle(orn1[2] + np.pi - orn_eef1[2])) \
#             else wrap_angle(orn1[2] + np.pi)  # minimize the delta yaw
#         yaw2 = orn2[2] if abs(wrap_angle(orn2[2] - orn_eef2[2])) < abs(wrap_angle(orn2[2] + np.pi - orn_eef2[2])) \
#             else wrap_angle(orn2[2] + np.pi)  # minimize the delta yaw

#         # the corresponding peg position
#         # pos_peg = get_link_pose(self.obj_ids['fixed'][1], self.obj_id - np.min(self._blocks) + 6)[0]  # 6 pegs
#         pos_peg = get_link_pose(self.obj_ids['fixed'][1],
#                                 self._pegs[self.obj_id - np.min(self._blocks) + 6])[0]  # 6 pegs

#         pos_mid1 = [pos_obj1[0],
#                     0. + pos_obj1[1] - pos_peg[1], pos_obj1[2] + 0.043 * self.SCALING]  # consider offset
#         pos_mid2 = [pos_obj2[0],
#                     0. + pos_obj2[1] - pos_peg[1], pos_obj2[2] + 0.043 * self.SCALING]  # consider offset

#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
#                                          pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
#                                          pos_obj2[0], pos_obj2[1]-0.005,
#                                          pos_mid2[2], yaw2, 0.5]))  # above object
#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
#                                          pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
#                                          pos_obj2[0], pos_obj2[1]-0.005,
#                                          pos_obj2[2] + (0.003 + 0.0102) * self.SCALING, yaw2, 0.5]))  # approach
#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
#                                          pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
#                                          pos_obj2[0], pos_obj2[1]-0.005,
#                                          pos_obj2[2] + (0.003 + 0.0102) * self.SCALING, yaw2, -0.5]))  # psm2 grasp
#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1],
#                                          pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
#                                          pos_obj2[0], pos_obj2[1]-0.005,
#                                          pos_mid2[2], yaw2, -0.5]))  # lift up

#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2] + 0.01 * self.SCALING, yaw1, 0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # move to middle

#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, 0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # psm1 pre grasp

#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2]+0.01, yaw2, -0.5]))  # psm1 grasp

#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2], yaw2, 0.5]))  # psm2 release
#         self._waypoints.append(np.array([pos_mid1[0], pos_mid1[1], pos_mid1[2], yaw1, -0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
#                                          yaw2, 0.5]))  # psm2 lift up

#         pos_place = [self.goal[0] + pos_obj1[0] - pos_peg[0],
#                      self.goal[1] + pos_obj1[1] - pos_peg[1], pos_mid1[2]]  # consider offset
#         self._waypoints.append(np.array([pos_place[0]-0.02, pos_place[1]-0.0035, pos_place[2], yaw1, -0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
#                                          yaw2, 0.5]))  # above goal
#         self._waypoints.append(np.array([pos_place[0]-0.02, pos_place[1]-0.0035, pos_place[2], yaw1, 0.5,
#                                          pos_mid2[0], pos_mid2[1], pos_mid2[2] + 0.01 * self.SCALING,
#                                          yaw2, 0.5]))  # above goal
#         self._waypoints_done = [False] * len(self._waypoints)

#     def _meet_contact_constraint_requirement(self):
#         # add a contact constraint to the grasped block to make it stable
#         if self.haptic is True:
#             # print(f'meet due to hardcoe')
#             return True
#         else:
#             pose = get_link_pose(self.obj_id, -1)
#             return pose[0][2] > self.goal[2] + 0.01 * self.SCALING  # reduce difficulty

#     def get_oracle_action(self, obs) -> np.ndarray:
#         """
#         Define a human expert strategy
#         """
#         # eleven waypoints executed in sequential order
#         action = np.zeros(10)
#         # haptic left
#         retrived_action = np.array([0, 0, 0, 0, 0], dtype = np.float32)
#         getDeviceAction_left(retrived_action)
#         # retrived_action-> x,y,z, angle, buttonState(0,1,2)
#         if retrived_action[4] == 2:
#             action[5+0] = 0
#             action[5+1] = 0
#             action[5+2] = 0
#             action[5+3] = 0            
#         else:
#             action[5+0] = retrived_action[2]*0.15
#             action[5+1] = retrived_action[0]*0.15
#             action[5+2] = retrived_action[1]*0.15
#             action[5+3] = -retrived_action[3]/math.pi*180*0.08
#         if retrived_action[4] == 0:
#             action[5+4] = 1
#         if retrived_action[4] == 1:
#             action[5+4] = -0.5

#         # # haptic right
#         retrived_action = np.array([0, 0, 0, 0, 0], dtype = np.float32)
#         getDeviceAction_right(retrived_action)
#         # retrived_action-> x,y,z, angle, buttonState(0,1,2)
#         if retrived_action[4] == 2:
#             action[0] = 0
#             action[1] = 0
#             action[2] = 0
#             action[3] = 0              
#         else:
#             action[0] = retrived_action[2]*0.15
#             action[1] = retrived_action[0]*0.15
#             action[2] = retrived_action[1]*0.15
#             action[3] = -retrived_action[3]/math.pi*180*0.08
#         if retrived_action[4] == 0:
#             action[4] = 1
#         if retrived_action[4] == 1:
#             action[4] = -0.5

#         return action

#     def _set_action_ecm(self, action):
#         action *= 0.01 * self.SCALING
#         pose_rcm = self.ecm.get_current_position()
#         pose_rcm[:3, 3] += action
#         pos, _ = self.ecm.pose_rcm2world(pose_rcm, 'tuple')
#         joint_positions = self.ecm.inverse_kinematics((pos, None), self.ecm.EEF_LINK_INDEX)  # do not consider orn
#         self.ecm.move_joint(joint_positions[:self.ecm.DoF])
    
#     def __del__(self):
#         stopScheduler()
#         closeTouch_left() 
#         closeTouch_right() 

if __name__ == "__main__":
    env = BiPegTransfer(render_mode='human')  # create one process and corresponding env

    env.test()
    env.close()
    time.sleep(2)
