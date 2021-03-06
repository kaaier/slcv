#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 27 15:00:44 2018

@author: ubuntu

由于yolov3使用darknet，对voc数据有特殊要求，需要采用voc_label.py预先转换好。
然后基于转换结果用本dataset进行打包。

参考：
https://github.com/eriklindernoren/PyTorch-YOLOv3

"""
import random
import os
import numpy as np

import torch

from torch.utils.data import Dataset
from PIL import Image
import torchvision.transforms as transforms

import matplotlib.pyplot as plt
import matplotlib.patches as patches

from skimage.transform import resize

import sys
# 检查python版本号，如果是py2则导入的是cElementTree, py3则导入ElementTree
if sys.version_info[0] == 2:
    import xml.etree.cElementTree as ET
else:
    import xml.etree.ElementTree as ET

class ListDataset(Dataset):
    """专门针对coco2014数据集
    """
    def __init__(self, list_path, img_size=416):
        # 获得所有图片地址
        with open(list_path, 'r') as file:
            self.img_files = file.readlines()
        # 
        self.label_files = [path.replace('images', 'labels').replace('.png', '.txt').replace('.jpg', '.txt') for path in self.img_files]
        self.img_shape = (img_size, img_size)
        self.max_objects = 50

    def __getitem__(self, index):

        #---------
        #  Image
        #---------

        img_path = self.img_files[index % len(self.img_files)].rstrip()
        img = np.array(Image.open(img_path))

        # Handles images with less than three channels
        while len(img.shape) != 3:
            index += 1
            img_path = self.img_files[index % len(self.img_files)].rstrip()
            img = np.array(Image.open(img_path))

        h, w, _ = img.shape
        dim_diff = np.abs(h - w)
        # Upper (left) and lower (right) padding
        pad1, pad2 = dim_diff // 2, dim_diff - dim_diff // 2
        # Determine padding
        pad = ((pad1, pad2), (0, 0), (0, 0)) if h <= w else ((0, 0), (pad1, pad2), (0, 0))
        # Add padding
        input_img = np.pad(img, pad, 'constant', constant_values=128) / 255.
        padded_h, padded_w, _ = input_img.shape
        # Resize and normalize
        input_img = resize(input_img, (*self.img_shape, 3), mode='reflect')
        # Channels-first
        input_img = np.transpose(input_img, (2, 0, 1))
        # As pytorch tensor
        input_img = torch.from_numpy(input_img).float()

        #---------
        #  Label
        #---------

        label_path = self.label_files[index % len(self.img_files)].rstrip()

        labels = None
        if os.path.exists(label_path):
            labels = np.loadtxt(label_path).reshape(-1, 5)
            # Extract coordinates for unpadded + unscaled image
            x1 = w * (labels[:, 1] - labels[:, 3]/2)
            y1 = h * (labels[:, 2] - labels[:, 4]/2)
            x2 = w * (labels[:, 1] + labels[:, 3]/2)
            y2 = h * (labels[:, 2] + labels[:, 4]/2)
            # Adjust for added padding
            x1 += pad[1][0]
            y1 += pad[0][0]
            x2 += pad[1][0]
            y2 += pad[0][0]
            # Calculate ratios from coordinates
            labels[:, 1] = ((x1 + x2) / 2) / padded_w
            labels[:, 2] = ((y1 + y2) / 2) / padded_h
            labels[:, 3] *= w / padded_w
            labels[:, 4] *= h / padded_h
        # Fill matrix
        filled_labels = np.zeros((self.max_objects, 5))
        if labels is not None:
            filled_labels[range(len(labels))[:self.max_objects]] = labels[:self.max_objects]
        filled_labels = torch.from_numpy(filled_labels)

        return img_path, input_img, filled_labels

    def __len__(self):
        return len(self.img_files)


class VOCDetection(Dataset):
    """专门针对VOC数据集的定义
    """
    def __init__(self, root, image_set, transform=None, target_transform=None, img_size = 416):
        """
            root: refers to the path you save the pascal_voc liked data;
            image_set: the subset such as 'train', 'val', 'test'
        """
        self.root = root
        self.image_set = image_set
        self.transform = transform
        self.target_transform = target_transform
        
        # 拼接3个核心文件夹地址： annotations, jpegimages, imagesets
        dataset_name = 'VOC2012'
        self._annopath = os.path.join(self.root, dataset_name, 'Annotations', '%s.xml')
        self._imgpath = os.path.join(self.root, dataset_name, 'JPEGImages', '%s.jpg')
        self._imgsetpath = os.path.join(self.root, dataset_name, 'ImageSets', 'Main', '%s.txt')
        # 打开train图片
        with open(self._imgsetpath % self.image_set) as f:
            self.ids = f.readlines()
        # 读取train地址: '000012', '000370'...总计2501个
        self.ids = [x.strip('\n') for x in self.ids]
        self.max_objects = 100
        self.img_shape = (img_size, img_size)

    def __getitem__(self, index):
        # 对数据集进行切片
        img_id = self.ids[index]
        # xml格式文件的操作调用ET.parse(addr).getroot()得到的root为？？？
        img = np.array(Image.open(self._imgpath % img_id).convert('RGB'))
        #print(self._imgpath % img_id)
        
        h, w, _ = img.shape
        dim_diff = np.abs(h - w)
        pad1, pad2 = dim_diff // 2, dim_diff - dim_diff // 2
        # Determine padding
        pad = ((pad1, pad2), (0, 0), (0, 0)) if h <= w else ((0, 0), (pad1, pad2), (0, 0))
        # Add padding 并归一化
        input_img = np.pad(img, pad, 'constant', constant_values=128) / 255.
        padded_h, padded_w, _ = input_img.shape
        # Resize and normalize
        input_img = resize(input_img, (*self.img_shape, 3), mode='reflect')
        # Channels-first
        input_img = np.transpose(input_img, (2, 0, 1))
        # As pytorch tensor
        input_img = torch.from_numpy(input_img).float()
        
        # 这部分有问题，xml格式没法做transform
#        target = ET.parse(self._annopath % img_id).getroot()
#        
#        if self.target_transform is not None:
#            target = self.target_transform(target)
#            
#        labels = None
        
        # 如果target存在,先转换为array,shape为(8,)
        from xmltodict import parse as parse_xml
        if os.path.exists(self._annopath % img_id):
            annotation = parse_xml(open(label_path).read())['annotation']
            objs = annotation.get('object', [])
            objs = objs if isinstance(objs, list) else [objs]
            labels = [
                [self.classes.index(o["name"]),
                 float(o["bndbox"]["xmin"]), float(o["bndbox"]["ymin"]),
                 float(o["bndbox"]["xmax"]), float(o["bndbox"]["ymax"])] for o in objs
            ]

            labels = np.array(labels)

        if len(target) > 0:
            target = np.array(target).reshape(-1,1)
            x1 = target[:,1]
            y1 = target[:,2]
            x2 = target[:,3]
            y2 = target[:,4]
            # transform the pascal form label to coco form
            labels = np.zeros((target.shape))
            labels[:,0] = target[:,0]
            labels[:,1] = (x1 + x2) / (2 * w)
            labels[:,2] = (y1 + y2) / (2 * h)
            labels[:,3] = (x2 - x1) / w
            labels[:,4] = (y2 - y1) / h
            x1 = w * (labels[:, 1] - labels[:, 3]/2)
            y1 = h * (labels[:, 2] - labels[:, 4]/2)
            x2 = w * (labels[:, 1] + labels[:, 3]/2)
            y2 = h * (labels[:, 2] + labels[:, 4]/2)
               
            # Adjust for added padding
            x1 += pad[1][0]
            y1 += pad[0][0]
            x2 += pad[1][0]
            y2 += pad[0][0]
            # Calculate ratios from coordinates
            labels[:, 1] = ((x1 + x2) / 2) / padded_w
            labels[:, 2] = ((y1 + y2) / 2) / padded_h
            labels[:, 3] *= float(w) / float(padded_w)
            labels[:, 4] *= float(h) / float(padded_h)
        
        filled_labels = np.zeros((self.max_objects, 5))
        if labels is not None:
            filled_labels[range(len(labels))[:self.max_objects]] = labels[:self.max_objects]
        else:
            print('no object')
        filled_labels = torch.from_numpy(filled_labels)

        return input_img, filled_labels

    def __len__(self):
        return len(self.ids)

    
class VOCDataset(Dataset):
    """参考voc dataset： https://github.com/jinyu121/PyTorchYOLOv2/blob/master/datasets.py
    """
    def __init__(self, base_path, list_name, classes, img_size=416, img_ext=".jpg"):

        self.files = [x.strip() for x in open(os.path.join(base_path, "ImageSets", "Main", list_name + ".txt"), 'r')]
        self.files = [(os.path.join(base_path, "JPEGImages", filename + img_ext),
                       os.path.join(base_path, "Annotations", filename + ".xml")) for filename in self.files]
        self.classes = classes
        self.img_shape = (img_size, img_size)
        self.max_objects = 50

    def __getitem__(self, index):

        # ---------
        #  Image
        # ---------

        img_path = self.files[index][0]
        img = io.imread(img_path)

        if len(img.shape) > 3:
            img = img[:, :, :3]
        elif len(img.shape) < 3:
            img = color.gray2rgb(img)

        h, w, _ = img.shape
        dim_diff = np.abs(h - w)
        # Upper (left) and lower (right) padding
        pad1, pad2 = dim_diff // 2, dim_diff - dim_diff // 2
        # Determine padding
        pad = ((pad1, pad2), (0, 0), (0, 0)) if h <= w else ((0, 0), (pad1, pad2), (0, 0))
        # Add padding
        input_img = np.pad(img, pad, 'constant', constant_values=128) / 255.
        padded_h, padded_w, _ = input_img.shape
        # Resize and normalize
        input_img = resize(input_img, (self.img_shape[0], self.img_shape[1], 3), mode='reflect', anti_aliasing=False)
        # Channels-first
        input_img = np.transpose(input_img, (2, 0, 1))
        # As pytorch tensor
        input_img = torch.from_numpy(input_img).float()

        # ---------
        #  Label
        # ---------

        label_path = self.files[index][1]

        labels = []
        if os.path.exists(label_path):
            annotation = parse_xml(open(label_path).read())['annotation']
            objs = annotation.get('object', [])
            objs = objs if isinstance(objs, list) else [objs]
            labels = [
                [self.classes.index(o["name"]),
                 float(o["bndbox"]["xmin"]), float(o["bndbox"]["ymin"]),
                 float(o["bndbox"]["xmax"]), float(o["bndbox"]["ymax"])] for o in objs
            ]

            labels = np.array(labels)

            # Extract coordinates for unpadded + unscaled image, and adjust for added padding
            x1 = labels[:, 1] + pad[1][0]
            y1 = labels[:, 2] + pad[0][0]
            x2 = labels[:, 3] + pad[1][0]
            y2 = labels[:, 4] + pad[0][0]

            # Calculate ratios from coordinates
            labels[:, 1] = ((x1 + x2) / 2) / padded_w
            labels[:, 2] = ((y1 + y2) / 2) / padded_h
            labels[:, 3] *= w / padded_w
            labels[:, 4] *= h / padded_h

        # Fill matrix
        if len(labels) < self.max_objects:
            filled_labels = np.pad(labels, ((0, self.max_objects - len(labels)), (0, 0)),
                                   'constant', constant_values=0.)
        else:
            filled_labels = labels[:self.max_objects]
        filled_labels = torch.from_numpy(filled_labels)

        return img_path, input_img, filled_labels

    def __len__(self):
        return len(self.files)

    @classmethod
    def get_info(cls, base_path, list_name, classes, img_ext=".jpg"):
        # Get the dataset info

        files = [x.strip() for x in open(os.path.join(base_path, "ImageSets", "Main", list_name + ".txt"), 'r')]

        meta = {}

        for filename in files:
            image_path = os.path.join(base_path, "JPEGImages", filename + img_ext)
            anno_path = os.path.join(base_path, "Annotations", filename + ".xml")

            annotation = parse_xml(open(anno_path).read())['annotation']
            objs = annotation.get('object', [])
            objs = objs if isinstance(objs, list) else [objs]
            objs = [
                {
                    'class_id': classes.index(o["name"]),
                    'bbox': [float(o["bndbox"]["xmin"]), float(o["bndbox"]["ymin"]),
                             float(o["bndbox"]["xmax"]), float(o["bndbox"]["ymax"])],
                    "difficult": int(o['difficult'])
                } for o in objs
            ]

            meta[filename] = {
                "image_path": image_path,
                "anno_path": anno_path,
                "size": {
                    "height": int(annotation["size"]["height"]),
                    "weight": int(annotation["size"]["width"])
                },
                "obj": objs
            }
        return meta
    
    
if __name__ == '__main__':
    
    test_id = 1
    
    if test_id == 1:
        root = '/home/ubuntu/MyDatasets/voc/VOCdevkit'
        trainset = VOCDetection(root=root, image_set='train', transform=None, img_size = 416)
        input_img, filled_labels = trainset[1]
    
    elif test_id == 2:
        root = '/home/ubuntu/MyDatasets/voc/VOCdevkit'
        
