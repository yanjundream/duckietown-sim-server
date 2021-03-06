#!/usr/bin/env python2
import cv2
import zmq
import numpy
import time
import rospy
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
import gazebo_ros
from sensor_msgs.msg import Image, CompressedImage
from std_srvs.srv import Empty
import numpy as np

SERVER_PORT=7777

# Camera image size
CAMERA_WIDTH = 100
CAMERA_HEIGHT = 100

# Camera image shape
IMG_SHAPE = (CAMERA_WIDTH, CAMERA_HEIGHT, 3)

def sendArray(socket, array):
    """Send a numpy array with metadata over zmq"""
    md = dict(
        dtype = str(array.dtype),
        shape = array.shape,
    )
    # SNDMORE flag specifies this is a multi-part message
    socket.send_json(md, flags=zmq.SNDMORE)
    return socket.send(array, flags=0, copy=True, track=False)

print('Starting up')
context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.bind("tcp://*:%s" % SERVER_PORT)


bridge = CvBridge()

last_good_img = None

class ImageStuff():
    def __init__(self):
        self.last_good_img = None

    def image_callback(self, msg):
        print("Received an image!")
        # setattr(msg, 'encoding', '')

        try:
            # Convert your ROS Image message to OpenCV2
            cv2_img = bridge.imgmsg_to_cv2(msg, "bgr8")
        except CvBridgeError, e:
            print(e)
        else:
            #
            # cv2.imwrite('camera_image.jpeg', cv2_img)

            self.last_good_img = cv2_img

imagestuff = ImageStuff()

rospy.init_node('gym', anonymous=True)
vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=5)
unpause = rospy.ServiceProxy('/gazebo/unpause_physics', Empty)
pause = rospy.ServiceProxy('/gazebo/pause_physics', Empty)
reset_proxy = rospy.ServiceProxy('/gazebo/reset_world', Empty)
image_topic = "/duckiebot/camera1/image_raw"
img_sub = rospy.Subscriber(image_topic, Image, imagestuff.image_callback)


# waiting for ROS to connect... TODO solve this with ROS callback
time.sleep(2)


while True:
    print('Waiting for a command')

    msg = socket.recv_json()
    print (msg)

    if msg['command'] == 'reset':
        print('resetting the simulation')
        #reset_proxy()
        # let it stabilize # temporary fix for duckiebot being too low
        unpause()
        time.sleep(1)
        pause()

    elif msg['command'] == 'action':
        print('received motor velocities')
        print(msg['values'])

        vel_cmd = Twist()
        left, right = tuple(msg['values'])

        if (left > 0 and right > 0) or (left < 0 and right < 0):
            vel_cmd.linear.x = 0.3 * left
            vel_cmd.angular.z = 0
        else:
            vel_cmd.linear.x = 0.05
            vel_cmd.angular.z = 0.3 * right

        vel_pub.publish(vel_cmd)
        unpause()
        time.sleep(.05) # this is hacky as fuck
        pause()
    else:
        assert False, "unknown command"

    # TODO: fill in this data
    # Send world position data, etc
    # Note: the Gym client needs this to craft a reward function
    socket.send_json(
        {
            # XYZ position
            "position": [0, 0, 0],

            # Are we properly sitting inside our lane?
            "inside_lane": True,

            # Are we colliding with a building or other car?
            "colliding": False,
        },
        flags=zmq.SNDMORE
    )

    # # Send a camera frame
    # img = numpy.ndarray(shape=IMG_SHAPE, dtype='uint8')
    #
    # # Note: image is encoded in RGB format
    # # Coordinates (0,0) are at the top-left corner
    # for j in range(0, CAMERA_HEIGHT):
    #     for i in range(0, CAMERA_WIDTH):
    #         img[j, i, 0] = j # R
    #         img[j, i, 1] = i # G
    #         img[j, i, 2] = 0 # B

    # only resize when we need
    img = cv2.resize(imagestuff.last_good_img, (CAMERA_WIDTH, CAMERA_HEIGHT))

    # BGR to RGB
    img = img[:,:,::-1]

    # to contiguous, otherwise ZMQ will complain
    img = np.ascontiguousarray(img, dtype=np.uint8)

    sendArray(socket, img)

    time.sleep(0.05)
