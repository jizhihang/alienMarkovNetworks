#!/usr/bin/env python

"""
Command-line utility to do N-class pixel-wise MRF segmentation.
"""

# SUMMARY: this is an N-class foreground/background labelling example:
#
# Usage:  ./sceneLabelN.py --clfrFn <classifierPkl> <imageName> 
#
# Example:
#
#     ./sceneLabelN.py --clfrFn classifier_msrc_rf_400-10_grid.pkl 3_7_s.bmp


import argparse

parser = argparse.ArgumentParser(description='Classify image and then apply MRF at the pixel level.')
parser.add_argument('--clfrFn', type=str, action='store', \
                        help='filename of pkl or csv superPixel classifier file')
parser.add_argument('--matFn', type=str, action='store', default=None,\
                    help='filename of matlab file for isprs')
parser.add_argument('infile', type=str, action='store', \
                        help='filename of input image to be classified')
parser.add_argument('--outfile', type=str, action='store', \
                        help='filename of output image with MRF inferred labels')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--interactive', action='store_true')
parser.add_argument('--K', type=float, action='store', default=0.1, \
                        help='Weighting for pairwise potential term in MRF.')
parser.add_argument('--nhoodSz', type=int, action='store', default=4, \
                        help='Neighbourhood connectivity for graph, must be 4 or 8.')
#parser.add_argument('--nbrPotentialMethod', type=str, action='store', \
#                        choices=['degreeSensitive', 'adjacencyAndDegreeSensitive'], default='degreeSensitive',\
#                        help='Neighbour potential method.  If adjacency is used, then --adjFn must be specified.')

args = parser.parse_args()

assert args.nhoodSz == 4 or args.nhoodSz == 8

import pickle as pkl
import sys
import numpy as np
import scipy
from matplotlib import pyplot as plt
import scipy.ndimage.filters
import cython_uflow as uflow
import classification
import amntools
import sklearn
import sklearn.ensemble
import pomio
import isprs

# parse args
clfrFn = args.clfrFn 
imgFn = args.infile

dbgMode = 0


#
# MAIN
#


precomputedMode = args.matFn != None
imgRGB = amntools.readImage( imgFn )
if args.verbose:
  plt.interactive(1)
  plt.imshow(imgRGB)
  plt.title('original image')
  #plt.waitforbuttonpress()
  plt.figure()

if precomputedMode == True:
  spix, classProbsLUT = isprs.loadISPRSResultFromMatlab( args.matFn )
  classLabs = spix.m_labels
  # map the labels to HxWxC class probabilities matrix
  classProbs = np.zeros( classLabs.shape + (classProbsLUT.shape[1],) )
  for c in range( classProbsLUT.shape[1] ):
    # Get a mask of matching pixels
    classProbs[ :,:, c ] = classProbsLUT[ classLabs, c ]
  colourMap = isprs.colourMap
  classLabels = isprs.classLabels
else:
  print 'Computing class probabilities...'
  print 'Loading classifier...'
  clfr = pomio.unpickleObject(clfrFn)
  ftype = 'classic'
  classLabs, classProbs = classification.classifyImagePixels(imgRGB, clfr, ftype, True)
  print 'done.  result size = ', classProbs.shape

  print ' classes = ', clfr.classes_
  # Transform class probs to the correct sized matrix.
  nbRows = imgRGB.shape[0]
  nbCols = imgRGB.shape[1]
  nbClasses = pomio.getNumClasses()

  cpnew = np.zeros( (nbRows, nbCols, nbClasses) )
  for i in range( classProbs.shape[2] ):
      # stuff this set of probs to new label
      cpnew[:,:,clfr.classes_[i]] = classProbs[:,:,i] 
  classProbs = cpnew
  del cpnew

maxLabel = np.argmax( classProbs, 2 )

pomio.showLabels(maxLabel, colourMap)
if args.verbose:
  plt.title('raw clfr labels')
  plt.figure()
  pomio.showClassColours( classLabels, colourMap )

  plt.draw()
  if args.interactive:
    plt.waitforbuttonpress()

#print classProbs

if dbgMode or args.verbose:
    for i in range( classProbs.shape[2] ):
        plt.imshow( classProbs[:,:,i] )
        plt.title( 'class %d: %s' % (i,classLabels[i]) )
        plt.waitforbuttonpress()

nhoodSz = args.nhoodSz
sigsq = amntools.estimateNeighbourRMSPixelDiff(imgRGB,nhoodSz) ** 2
print "Estimated neighbour RMS pixel diff = ", np.sqrt(sigsq)

print "Performing maxflow for various smoothness K..."

# In Shotton, K0 and K in the edge potentials are selected manually from
# validation data results.
K0 = 0#0.5

if args.verbose:
  plt.figure()
# for K in np.linspace(1,100,10):
#for K in np.logspace(1,3,3):

# def nbrCallback( pixR, pixG, pixB, nbrR, nbrG, nbrB ):
#    #print "*** Invoking callback"
#    idiffsq = (pixR-nbrR)**2 + (pixG-nbrG)**2 + (pixB-nbrB)**2
#    #idiffsq = (pixB-nbrB)**2
#    res = np.exp( -idiffsq / (2 * sigsq) )
#    #print res
#    # According to Shotton, adding the constant can help remove
#    # isolated pixels.
#    res = K0 + res * K
#    return res
#
# segResult = uflow.inferenceNCallback( \
#     imgRGB.astype(float),\
#     -np.log( np.maximum(1E-10, np.ascontiguousarray(classProbs) ) ), \
#     'abswap',\
#     nhoodSz, \
#     nbrCallback )

nbrPotentialMethod = 'contrastSensitive'
nbrPotentialParams = [K0,args.K,sigsq]

print 'size of class probs = ', classProbs.shape

segResult = uflow.inferenceN( \
    imgRGB.astype(float),\
    -np.log( np.maximum(1E-10, np.ascontiguousarray(classProbs) ) ), \
    'abswap',\
    nhoodSz, \
    nbrPotentialMethod, np.ascontiguousarray(nbrPotentialParams) )

# Show the result.
pomio.showLabels(segResult, colourMap)
if args.verbose:
  plt.title( 'Segmentation with K=%f' % args.K )
  plt.draw()
print "labelling result, K = ", args.K 


if args.outfile and len(args.outfile)>0:
    print 'Writing output label file %s' % args.outfile
    outimg = pomio.msrc_convertLabelsToRGB( segResult, colourMap )
    amntools.writeImage(args.outfile, outimg)
    print '   done.'


if args.verbose:
  if args.interactive:
      plt.waitforbuttonpress()

  if args.interactive:
    plt.interactive(False)
    plt.show()

