# coding=utf-8

import unittest
import tempfile
import shutil
import os
import random
import pickle
from threading import Thread

from pqueue import Queue, Empty

class TestSuite_PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp()

    def tearDown(self):
        #shutil.rmtree(cls.path, ignore_errors=True)
        pass

    def test_OpenCloseSingle(self):
        """Write 1 item, close, reopen checking if same item is there"""

        q = Queue(self.path)
        q.put('var1')
        del q
        q = Queue(self.path)
        self.assertEqual(1, q.qsize())
        self.assertEqual('var1', q.get())

    def test_OpenCloseOneHundred(self):
        """Write 1000 items, close, reopen checking if all items are there"""

        q = Queue(self.path)
        for i in range(1000):
            q.put('var%d' % i)
        del q
        q = Queue(self.path)
        self.assertEqual(1000, q.qsize())
        for i in range(1000):
            self.assertEqual('var%d' % i, q.get())
        with self.assertRaises(Empty):
            q.get_nowait()

    def test_PartialWrite(self):
        """Test recovery from previous crash w/ partial write"""

        q = Queue(self.path)
        for i in range(100):
            q.put('var%d' % i)
        del q
        with open(os.path.join(self.path, 'q00000'), 'ab') as f:
            pickle.dump('文字化け', f)
        q = Queue(self.path)
        self.assertEqual(100, q.qsize())
        for i in range(100):
            self.assertEqual('var%d' % i, q.get())
        with self.assertRaises(Empty):
            q.get_nowait()

    def test_RandomReadWrite(self):
        """Test random read/write"""

        q = Queue(self.path)
        for i in range(1000):
            read = random.getrandbits(1)
            if read:
                try:
                    n = q.qsize()
                    data = q.get_nowait()
                except Empty:
                    self.assertEqual(0, n)
            else:
                q.put('var%d', random.getrandbits(16))

    def test_MultiThreaded(self):
        """Create consumer and producer threads, check parallelism"""

        q = Queue(self.path)
        def producer():
            for i in range(1000):
                q.put('var%d' % i)

        def consumer():
            for i in range(1000):
                q.get()

        c = Thread(target = consumer)
        c.start()
        p = Thread(target = producer)
        p.start()
        c.join()
        p.join()
        with self.assertRaises(Empty):
            q.get_nowait()

