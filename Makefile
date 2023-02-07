.PHONY: clean requirements sdist

#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
PYTHON_INTERPRETER = python

#################################################################################
# COMMANDS                                                                      #
#################################################################################

## Install python dependencies
requirements:
	$(PYTHON_INTERPRETER) -m pip install -U pip setuptools wheel
	$(PYTHON_INTERPRETER) -m pip install -r requirements.txt

dist_requirements:
	$(PYTHON_INTERPRETER) -m pip install -U pip setuptools setuptools-git wheel

sdist: dist_requirements clean 
	$(PYTHON_INTERPRETER) setup.py sdist

## Delete all compiled Python files
clean:
	rm -R build dist &>/dev/null || :
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec "rm -R {} ;" &>/dev/null || :

