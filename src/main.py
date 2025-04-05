#!/usr/bin/env python

import os
try:
    from mega import Mega
except ImportError:
    Mega = None
