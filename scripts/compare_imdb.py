#!/bin/env python
import os
from ptpapi import PTPAPI
from cgapi import CGAPI
import tty, sys, termios

class _GetchUnix:
    def __call__(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

getch = _GetchUnix()

def sizeof_fmt(num):
    for x in ['bytes','KB','MB','GB','TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

class cmdCtl:
    def __init__(self, filename=None):
        self.ptp = PTPAPI()
        self.ptp.login()
        self.cg = CGAPI()
        self.cg.login()
        self.index = -1
        if filename:
            self.openFile(filename)
    
    def next(self):
        if self.index < len(self.IDs)-1:
            self.index += 1

    def previous(self):
        if self.index > 0:
            self.index -= 1

    def goto(self):
        newIndex = int(raw_input('Go to index: '))
        if newIndex > 0 and newIndex < len(self.IDs)-1:
            self.index = newIndex
            
    def dummy(self):
        pass

    def cgInfo(self, imdbID):
        data = self.cg.search({'search': imdbID})
        for t in data:
            print '{0:<26} {1} {2}'.format(t['Title'][:25], str(t['Seeders']), t['Size'])

    def ptpInfo(self, imdbID):
        j = self.ptp.search({'searchstr': imdbID})
        for m in j['Movies']:
            print 'Title:', m['Title']
            for t in m['Torrents']:
                print '{0:<26} {1} {2}'.format(t['ReleaseName'][:25], str(t['Seeders']), sizeof_fmt(int(t['Size'])))

    def openFile(self, filename):
        with open(filename, 'r') as fh:
            self.IDs = [l.strip() for l in fh.readlines()]
            print '%s loaded.' % filename
            self.index = 0

    def list(self):
        for i in range(max(0, self.index-10), min(len(self.IDs), self.index+10)):
            print "%i: %s" % (i, self.IDs[i])

    def showHelp(self):
        print """h: Help
q: Quit
n: Next
p: Previous
g: Goto
f: Find
l: List
r: reload"""

    def commandLoop(self):
        ch = 'r'
        cmdArray = {'h': self.showHelp,
                    'q': self.dummy,
                    'g': self.goto,
                    #'f': self.find,
                    'r': self.dummy,
                    'n': self.next,
                    'l': self.list,
                    'p': self.previous}
        while ch != 'q':
            sys.stdout.write('% ')
            ch = getch()
            if ch in cmdArray.keys():
                os.system('cls' if os.name == 'nt' else 'clear')
                cmdArray[ch]()
                if self.index >= 0 and ch not in 'hql':
                    print '%i: %s' % (self.index, self.IDs[self.index].strip())
                    self.ptpInfo(self.IDs[self.index])
                    print 'CG:'
                    self.cgInfo(self.IDs[self.index])
            else:
                print 'Command not found for %s' % ch

if __name__ == '__main__':
    c = cmdCtl('imdb.txt')
    c.commandLoop()
