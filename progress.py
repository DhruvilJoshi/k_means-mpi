import os
from time import sleep, time
from threading import Timer, Lock
from mpi4py import MPI
from math import ceil
import sys

BORDER_H = "-"
BORDER_V = "|"
BORDER_T = "+"
ROWS = 5

MESSAGE_TAG = 98
PROGRESS_TAG = 99

SEC_CHANCE = 0.05
UPDATE_TIMEOUT = 2.0

class ProgressManager(object):
    """ 256 threads tryin to blast updates gets out of hand! """

    def __init__(self, comm, myrank, size, maxwidth=50):
        self.comm = comm
        self.myrank = myrank
        self.size = size
        self.running = False
        self.last_message = ''
        self.last_send_message = 0
        self.last_progress = (0,1)
        self.last_send_progress = 0
        self.request_m = None
        self.request_p = None

        # these are for node 0
        self.maxwidth = maxwidth
        self.messages = ['' for x in xrange(size)]
        self.progress = [[0,1] for x in xrange(size)]
        self.dirtylock = Lock()
        self.dirty = set()
        if myrank == 0:
            #self.rows, self.columns = os.popen('stty size', 'r').read().split()
#            self.rows = 63
#            self.columns = 105
            self.rows = 71
            self.columns = 211

    def start_handling(self):
        if self.myrank == 0:
            self.start_handling_root()
    def client_send_message(self):
        if self.request_m is None and self.last_message is not None:
            self.request_m = self.comm.isend(self.last_message, dest=0, tag=98)
            self.last_message = None
        if self.request_m is not None:
            res = self.request_m.test()
            if res[0]:
                self.request_m = None
        self.last_send_message = time()
    def client_send_progress(self):
        if self.request_p is None and self.last_progress is not None:
            self.request_p = self.comm.isend(self.last_progress, dest=0, tag=99)
            self.last_progress = None
        if self.request_p is not None:
            res = self.request_p.test()
            if res[0]:
                self.request_p = None
        self.last_send_progress = time()
    def client_send(self):
        self.client_send_message()
        self.client_send_progress()
            
    def start_handling_root(self):
        self.running = True
        self._redraw(clear=True)
        def handler():
            handle()
        def handle():
            attempt = 0
            while attempt < 3:
                # get a new request if we're not already waiting for one
                if self.request_m is None:
                    self.request_m = self.comm.irecv(source=MPI.ANY_SOURCE, tag=98)
                if self.request_p is None:
                    self.request_p = self.comm.irecv(source=MPI.ANY_SOURCE, tag=99)
                # check the status
                status = MPI.Status()
                res = MPI.Request.testany((self.request_m, self.request_p), status=status)
                if res[1]:
                    if res[0] == 0:
                        self.messages[status.Get_source()] = res[2]
                        self.request_m = None
                        with self.dirtylock:
                            self.dirty.add(status.Get_source())
                    elif res[0] == 1:
                        self.progress[status.Get_source()] = res[2]
                        self.request_p = None
                        with self.dirtylock:
                            self.dirty.add(status.Get_source())
                else:
                    sleep(SEC_CHANCE)
                    attempt += 1
            self._redraw()
            if self.running:
                Timer(UPDATE_TIMEOUT, handler).start()
        handler()

    def _redraw(self, clear=False):
#        try:
#            self.rows, self.columns = os.popen('stty size', 'r').read().split()
#        except ValueError:
#            pass

        pcols = self.columns / self.maxwidth
        prows = int(ceil(self.size / float(pcols)))

        def _blit_status(i, j):
            rank = i*pcols + j
            r = i * ROWS + 1
            c = j * self.maxwidth + 1
            if r + 4 > self.rows:
                return       # out of screen
            sys.stderr.write("\033[{};{}H".format(r,c))
            sys.stderr.write("{c}{h:-^{len}}{c}".format(c=BORDER_T,h=BORDER_H,len=self.maxwidth-1))
            sys.stderr.write("\033[{};{}H".format(r+1,c))
            sys.stderr.write("{v}{:{len}}".format("", v=BORDER_V, len=self.maxwidth-1))
            sys.stderr.write("\033[{};{}H".format(r+2,c))
            sys.stderr.write("{v}{message:^{len}}".format(message=self.messages[rank],v=BORDER_V,len=self.maxwidth-1))
            sys.stderr.write("\033[{};{}H".format(r+3,c))
            sys.stderr.write("{v}{progress:^{len}}".format(progress=self._get_progress_string(*self.progress[rank]),
                                            len=self.maxwidth-1,
                                            v=BORDER_V))
            sys.stderr.write("\033[{};{}H".format(r+4,c))
            sys.stderr.write("{v}{:{len}}".format("", v=BORDER_V, len=self.maxwidth-1))

        if clear:
            sys.stderr.write("\033[2J")     # clear the screen
            for i in xrange(prows):
                for j in xrange(pcols):
                    rank = i*pcols + j
                    if rank > self.size - 1:
                        break
                    _blit_status(i,j)
        else:
            dirty = self.dirty.copy()
            with self.dirtylock:
                self.dirty = set()
            for rank in dirty:
                i = rank / pcols
                j = rank - i*pcols
                _blit_status(i,j)

    def _get_progress_string(self, comp, total):
        length = self.maxwidth - 25
        perc_done = comp / float(total)
        progress = "#" * int((comp / float(total)) * length)
        output = "{:6.2f}%  [{:{length}}] {}/{}".format(perc_done * 100, 
                                                    progress, comp, total,
                                                    length=length)
        return output

    def update_text(self, message):
        """ format a message for printing and send it to the master node """
        # move up two lines and spit out the pass number, and percentage done
        if self.myrank > 0:
            self.last_message = message
            if time() - self.last_send_message > UPDATE_TIMEOUT:
                self.client_send()
        else:
            self.messages[0] = message
            with self.dirtylock:
                self.dirty.add(0)

    def update_progress(self, comp, total):
        if self.myrank > 0:
            self.last_progress = (comp,total)
            if time() - self.last_send_progress > UPDATE_TIMEOUT:
                self.client_send()
        else:
            self.progress[0] = (comp, total)
            with self.dirtylock:
                self.dirty.add(0)
