#
# Copyright (c) 2015, NVIDIA CORPORATION.  All rights reserved.
#
import logging
import os
import select
import sys
import time
import traceback
import subprocess
import sys

from stat import S_ISDIR

DEFAULT_CONNECTION_TIMEOUT=3600
BUFF_SIZE = 10*1024*1024  # 10MB

class ParamikoModuleFactory:
    """
    Detached paramiko creation.
    """
    @staticmethod
    def create():
        try:
            return __import__("paramiko")
        except ImportError, e:
            logger = logging.getLogger(__name__)
            logger.error(e)
            raise e

class ParamikoUtil(object):
    """
    Utility class providing file transfer and execution features
    through Paramiko library.
    """
    logger = logging.getLogger(__name__)

    def __init__(self, username, password, ip, port=22):
        # NOTE: some internal methods (of this class) are invoked using multiprocessing.Process
        # DO NOT bind an attribute to this instance if the attribute cannot be pickled
        # e.g. logger, paramiko library etc.

        self.ip = ip
        self.port = port
        self.username = username
        self.password = password

    def _createClient(self):
        paramiko = ParamikoModuleFactory.create()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=self.ip, port=self.port, username=self.username,
                       password=self.password, timeout=DEFAULT_CONNECTION_TIMEOUT)
        return client

    def copyFile(self, localpath, remotepath):
        client = self._createClient()
        sftp = client.open_sftp()
        sftp.put(localpath, remotepath)
        sftp.close()

    def execute(self, cmd, buffSize=BUFF_SIZE):
        """
        Implementation of 'execute' method.
        """
        client = self._createClient()
        print cmd
        stdin, stdout, stderr = client.exec_command(cmd)
        if "sudo" in cmd:
            stdin.write("vrlslave\n")
        print stdout.read()
        print stderr.read()
        client.close()

def setup(util):
    out = subprocess.check_output("python setup.py --command-packages=stdeb.command bdist_deb", shell=True)
    out = subprocess.check_output("ls deb_dist/*.deb", shell=True).strip()
    print out
    util.copyFile(out, "/tmp/foo")
    util.execute("sudo dpkg -i /tmp/foo")

def cleanup(util):
    util.execute("sudo apt-get remove python-allspeak-boardcontrol")
    # TODO execute apt-get install -f
    util.execute("sudo apt-get install python-allspeak-boardcontrol")

def performBoardOperation(util, boardControl, platform, operation):
    #util.execute('python -c "import os; print \\"foo\\""')
    util.execute('python -c "from allspeak.boardcontrol import BoardControl as b; b1 = b.factory(\\"{}\\")(target=\\"{}\\");b1.{}()"'.format(boardControl, platform, operation))
    util.execute("lsusb")

if __name__ == '__main__':
    machine = sys.argv[1]
    util = ParamikoUtil(machine, "vrlslave", machine)
    """
    Usage
    * python packageHandler machineName operation [options]

    # Supported operations & their options
    * setup
    * cleanup
    * execute cmd
    * boardControlOp debugBoardName platform

    Ex: To install a package. Go to dir containing setup.py and run
    "python packageHandler.py ausvrl3584 setup"


    Ex: To execute powerCycle on the board
    "python packageHandler.py ausvrl3584 powerCycle pm342 p3407-0"
    """

    operation = sys.argv[2]
    if operation == "setup":
        setup(util)
    elif operation == "cleanup":
        cleanup(util)
    elif operation == "execute":
        util.execute(sys.argv[3])
    else:
        performBoardOperation(util, sys.argv[3], sys.argv[4], operation)
