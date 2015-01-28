coveralls

echo $TRAVIS_PULL_REQUEST $TRAVIS_BRANCH

#if [[ "$TRAVIS_PULL_REQUEST" == "true" ]]; then
#    echo "This is a pull request. No deployment will be done."; exit 0
#fi


#if [[ "$TRAVIS_BRANCH" != "master" ]]; then
#    echo "No deployment on BRANCH='$TRAVIS_BRANCH'"; exit 0
#fi

echo $BINSTAR_TOKEN

if [[ "2.7" =~ "$python" ]]; then
    conda install --yes binstar jinja2
    binstar -t ${BINSTAR_TOKEN}  upload  --force --u omnia -p openpathsampling-dev $HOME/miniconda/conda-bld/linux-64/opentis-dev-*
fi

echo "Not yet uploading to s3."

exit 0

if [[ "$python" != "2.7" ]]; then
    echo "No deploy on PYTHON_VERSION=${python}"; exit 0
fi


# Create the docs and push them to S3
# -----------------------------------

# Install stuff for running the example IPython notebooks

# sudo apt-get install -qq pandoc         # notebook -> rst
# conda install --yes matplotlib scikit-learn sphinx==1.2.3 boto ipython-notebook jinja2
# pip install numpydoc runipy==0.0.4                      # example notebooks

# Install OpenMM for a couple of the the examples
# conda config --add channels http://conda.binstar.org/omnia
# conda install --yes openmm
# conda list -e

cd docs && make html && cd -
# python devtools/ci/push-docs-to-s3.py
