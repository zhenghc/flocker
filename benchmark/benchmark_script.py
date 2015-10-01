from sys import argv

from twisted.internet.task import react

from benchmark_sketch import driver

react(driver, argv[1:])
