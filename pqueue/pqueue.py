"""A single process, persistent multi-producer, multi-consumer queue."""

import pickle
import os
import struct
import tempfile
import fcntl
from contextlib import closing

import sys
if sys.version_info < (3, 0):
    from Queue import Queue as SyncQ
else:
    from queue import Queue as SyncQ


TEMP_SUBDIRECTORY = '_temp'

def _truncate(fn, length):
    with open(fn, 'a') as fd:
        os.ftruncate(fd, length)

class Queue(SyncQ):

    """Create a persistent queue object on a given path.

    The argument path indicates a directory where enqueued data should be
    persisted. If the directory doesn't exist, one will be created. If maxsize
    is <= 0, the queue size is infinite. The optional argument chunksize
    indicates how many entries should exist in each chunk file on disk.
    """
    def __init__(self, path, maxsize=0, chunksize=100, temp_subdir=False):
        self.path = path
        # temp_subdir is used for overriding temp file location, by
        # explicitly indicating that it must be a subdirectory of the
        # path used for persisting the elements. Reference:
        # https://github.com/balena/python-pqueue/issues/1
        self.path_temp = None
        if temp_subdir:
            self.path_temp = os.path.join(path, TEMP_SUBDIRECTORY)
            if not os.path.exists(self.path_temp):
                os.makedirs(self.path_temp)

        self.chunksize = chunksize
        SyncQ.__init__(self, maxsize)
        self.info = self._loadinfo()
        # truncate head case it contains garbage
        hnum, hcnt, hoffset = self.info['head']
        headfn = self._qfile(hnum)
        if os.path.exists(headfn):
            if hoffset < os.path.getsize(headfn):
                _truncate(headfn, hoffset)
        # let the head file open
        self.headf = self._openchunk(hnum, 'ab+')
        # let the tail file open
        tnum, _, toffset = self.info['tail']
        self.tailf = self._openchunk(tnum)
        self.tailf.seek(toffset)
        # update unfinished tasks with the current number of enqueued tasks
        self.unfinished_tasks = self.info['size']
        # optimize info file updates
        self.update_info = True

    def _init(self, maxsize):
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def _qsize(self, len=len):
        return self.info['size']

    def _put(self, item):
        pickle.dump(item, self.headf)
        self.headf.flush()
        hnum, hpos, _ = self.info['head']
        hpos += 1
        if hpos == self.info['chunksize']:
            hpos = 0
            hnum += 1
            self.headf.close()
            self.headf = self._openchunk(hnum, 'ab+')
        self.info['size'] += 1
        self.info['head'] = [hnum, hpos, self.headf.tell()]
        self._saveinfo()

    def _get(self):
        tnum, tcnt, toffset = self.info['tail']
        hnum, hcnt, _ = self.info['head']
        if [tnum, tcnt] >= [hnum, hcnt]:
            return None
        data = pickle.load(self.tailf)
        toffset = self.tailf.tell()
        tcnt += 1
        if tcnt == self.info['chunksize'] and tnum <= hnum:
            tcnt = toffset = 0
            tnum += 1
            self.tailf.close()
            os.remove(self.tailf.name)
            self.tailf = self._openchunk(tnum)
        self.info['size'] -= 1
        self.info['tail'] = [tnum, tcnt, toffset]
        self.update_info = True
        return data

    def task_done(self):
        SyncQ.task_done(self)
        if self.update_info:
            self._saveinfo()
            self.update_info = False

    def _openchunk(self, number, mode='r'):
        return open(self._qfile(number), mode)

    def _loadinfo(self):
        infopath = self._infopath()
        if os.path.exists(infopath):
            with open(infopath) as f:
                info = pickle.load(f)
        else:
            info = {
                'chunksize': self.chunksize,
                'size': 0,
                'tail': [0, 0, 0],
                'head': [0, 0, 0],
            }
        return info

    def _saveinfo(self):
        tmpfd, tmpfn = tempfile.mkstemp(dir=self.path_temp)
        os.write(tmpfd, pickle.dumps(self.info))
        os.close(tmpfd)
        # POSIX requires that 'rename' is an atomic operation
        os.rename(tmpfn, self._infopath())

    def _qfile(self, number):
        return os.path.join(self.path, 'q%05d' % number)

    def _infopath(self):
        return os.path.join(self.path, 'info')

