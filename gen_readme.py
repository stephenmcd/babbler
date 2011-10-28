#!/usr/bin/env python

from subprocess import Popen, PIPE

import babbler

section = lambda a, b, c: "\n".join(["", a, b * len(a), c])

with open("README.rst", "wb") as readme:
    readme.write(section("Babbler", "=", babbler.__doc__))
    help = Popen(["./babbler/__init__.py", "-h"], stdout=PIPE).communicate()
    readme.write(section("Options", "-", help[0].split("Options:")[1]))
