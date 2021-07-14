# -*- coding: utf-8 -*-
"""
Zegami Ltd.
Apache 2.0
"""

import base64
import io
import os
import numpy as np
from PIL import Image


class _Annotation():
    """Base (abstract) class for annotations."""

    # Define the string annotation TYPE in child classes
    TYPE = None
    UPLOADABLE_DESCRIPTION = None

    def __init__(self, collection, annotation_data, source=None):
        """!! STOP !! Instantiate a non-hidden subclass instead.

        Each subclass should call this __init__ AFTER assignment of members
        so that checks can be performed.

        If making a new annotation to upload, use collection.upload_annotation
        instead.
        """
        self._collection = collection  # Collection instance
        self._source = source  # Source instance
        self._data = annotation_data  # { imageset_id, image_index, type, annotation }

    @property
    def collection():
        pass

    @collection.getter
    def collection(self):
        return self._collection

    @property
    def source():
        pass

    @source.getter
    def source(self):
        return self._source

    @property
    def _image_index():
        pass

    @_image_index.getter
    def _image_index(self):
        assert 'image_index' in self._data.keys(), 'Annotation\'s _data did '\
            'not contain \'image_index\': {}'.format(self._data)
        return self._data['image_index']

    @property
    def row_index():
        pass

    @row_index.getter
    def row_index(self):
        lookup = self.collection._get_image_meta_lookup(self.source)
        return lookup.index(self._image_index)

    @property
    def _imageset_id():
        pass

    @_imageset_id.getter
    def _imageset_id(self):
        return self.collection._get_imageset_id(self.source)

    # -- Abstract/virtual, must be implemented in children --

    @classmethod
    def create_uploadable(cls) -> None:
        """Extend in children to include actual annotation data."""
        return {
            'type' : cls.TYPE,
            'format' : None,
            'annotation' : None
        }

    def view(self):
        """Abstract method to view a representation of the annotation."""
        return NotImplementedError('\'view\' method not implemented for annotation type: {}'.format(self.TYPE))


class AnnotationMask(_Annotation):
    """An annotation comprising a bitmask and some metadata.

    To view the maskas an image, use mask.view().

    Note: Providing imageset_id and image_index is not mandatory and can be
    obtained automatically, but this is slow and can cause unnecessary
    re-downloading of data. """

    TYPE = 'mask'
    UPLOADABLE_DESCRIPTION = 'Mask annotation data includes the actual mask (as a base64 '\
        'encoded string), a width and a height.'

    def __init__(
        self, collection, row_index, source=None, from_filepath=None,
        from_url=None, imageset_id=None, image_index=None):

        super(AnnotationMask, self).__init__(self, collection, row_index, source,
        from_filepath, from_url, imageset_id, image_index)

    @classmethod
    def create_uploadable(cls, bool_mask, class_id):
        """Creates a data package ready to be uploaded with a collection's .upload_annotation().

        Note: The output of this is NOT an annotation, it is used to upload
        annotation data to Zegami, which when retrieved will form an
        annotation.
        """
        # NOT TESTED

        assert type(bool_mask) == np.ndarray,\
            'Expected bool_mask to be a numpy array, not a {}'.format(type(bool_mask))
        assert bool_mask.dtype == bool,\
            'Expected bool_mask.dtype to be bool, not {}'.format(bool_mask.dtype)
        assert len(bool_mask.shape) == 2,\
            'Expected bool_mask to have a shape of 2 (height, width), not {}'.format(bool_mask.shape)

        h, w = bool_mask.shape

        # Encode the mask array as a 1 bit PNG encoded as base64
        mask_image = Image.fromarray(bool_mask.astype('uint8') * 255).convert('1')
        mask_buffer = io.BytesIO()
        mask_image.save(mask_buffer, format='PNG')
        byte_data = mask_buffer.getvalue()
        mask_b64 = base64.b64encode(byte_data)
        mask_string = "data:image/png;base64,{}".format(mask_b64.decode("utf-8"))
        bounds = cls.get_bool_mask_bounds(bool_mask)
        roi = {
            'xmin' : int(bounds['left']),
            'xmax' : int(bounds['right']),
            'ymin' : int(bounds['top']),
            'ymax' : int(bounds['bottom']),
            'width' : int(bounds['right'] - bounds['left']),
            'height' : int(bounds['bottom'] - bounds['top'])
        }
        
        data = {
            'mask' : mask_string,
            'width' : int(w),
            'height' : int(h),
            'score' : None,
            'roi' : roi
        }

        uploadable = super().create_uploadable()
        uploadable['format'] = '1UC1'
        uploadable['annotation'] = data
        uploadable['class_id'] = int(class_id)
        
        return uploadable

    def view(self):
        """View the mask as an image."""
        # NOT TESTED
        im = Image.fromarray(self.mask_uint8)
        im.show()

    @property
    def mask_uint8():
        pass

    @mask_uint8.getter
    def mask_uint8(self):
        return self.mask_bool.astype(np.uint8) * 255

    @property
    def mask_bool():
        pass

    @mask_bool.getter
    def mask_bool(self):
        a = self._get_bool_arr()
        assert len(a.shape) == 2, 'Invalid mask_bool shape: {}'.format(a.shape)
        assert a.dtype == bool, 'Invalid mask_bool dtype: {}'.format(a.dtype)
        return a

    @staticmethod
    def _read_bool_arr(local_fp):
        """Reads the boolean array from a locally stored file.

        Useful for creation of upload package.
        """
        # NOT FINISHED
        assert os.path.exists(local_fp), 'File not found: {}'.format(local_fp)
        assert os.path.isfile(local_fp), 'Path is not a file: {}'.format(local_fp)
        arr = np.array(Image.open(local_fp), dtype='uint8')
    
    @staticmethod
    def parse_bool_masks(bool_masks):
        ''' Checks the masks for correct data types, and ensures a shape of
        [h, w, N]. '''
        
        assert type(bool_masks) == np.ndarray,\
            'Expected bool_masks to be a numpy array, not {}'.format(type(bool_masks))
            
        assert bool_masks.dtype == bool,\
            'Expected bool_masks to have dtype == bool, not {}'.format(bool_masks.dtype)
            
        # If there is only one mask with no third shape value, insert one
        if len(bool_masks.shape) == 2:
            bool_masks = np.expand_dims(bool_masks, -1)
            
        return bool_masks
    
    @classmethod
    def get_bool_mask_bounds(cls, bool_mask):
        
        bool_mask = cls.parse_bool_masks(bool_mask)[:,:,0]
        
        rows = np.any(bool_mask, axis=1)
        cols = np.any(bool_mask, axis=0)
        
        try:
            top, bottom = np.where(rows)[0][[0, -1]]
            left, right = np.where(cols)[0][[0, -1]]
        except:
            top, bottom, left, right = 0, 0, 0, 0
        
        return { 'top' : top, 'bottom' : bottom, 'left' : left, 'right' : right }
