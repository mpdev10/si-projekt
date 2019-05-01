import json
import os

import cv2
import numpy as np
from pandas.io.json import json_normalize
from skimage import io


class BDDFormatStateDataset:

    def __init__(self, root, transform=None, target_transform=None,
                 dataset_type='train', label_file=None):
        self.root = root
        self.transform = transform
        self.target_transform = target_transform
        self.dataset_type = dataset_type.lower()
        self.label_file = label_file
        self.data, self.class_names, self.class_dict = self._read_data()
        self.min_image_num = -1
        self.ids = [info['image_id'] for info in self.data]

        self.class_stat = None

    def _read_data(self):
        annotation_file = f"{self.root}/sub-{self.dataset_type}-annotations.json"

        with open(annotation_file) as f:
            annotations = json.load(f)
        annotations = json_normalize(annotations)
        if self.label_file is not None:
            label_file_name = f"{self.root}/{self.label_file}"
            if os.path.isfile(label_file_name):
                class_string = ""
                with open(label_file_name, 'r') as infile:
                    for line in infile:
                        class_string += line.rstrip()
                class_names = class_string.split(',')
                class_names.insert(0, 'NA')
        else:
            normalized_list = annotations.labels.apply(lambda labels: list() if not labels else list(labels))
            categories = set()
            for labels in normalized_list:
                for label in labels:
                    categories.add(label['attributes']['CAR_STATE'][1])
            class_names = ['NA'] + sorted(list(categories))
        class_dict = {class_name: i for i, class_name in enumerate(class_names)}
        data = []

        for image, group in annotations.groupby('name'):
            labels = None
            boxes = None
            for labels_l in group.labels:
                if labels_l:
                    for label in labels_l:
                        box = label['box2d']
                        curr_box = np.array([[box['x1'], box['y1'], box['x2'], box['y2']]]).astype(np.float32)
                        if boxes is None:
                            boxes = curr_box
                            labels = np.array([class_dict[label['attributes']['CAR_STATE'][1]]])
                        else:
                            boxes = np.vstack((boxes, curr_box))
                            labels = np.append(labels, [class_dict[label['attributes']['CAR_STATE'][1]]])
            if boxes is not None:
                data.append({
                    'image_id': image,
                    'boxes': boxes,
                    'labels': labels
                })

        return data, class_names, class_dict

    def _read_image(self, image_id):
        image = io.imread(image_id)
        if image.shape[2] == 1:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return image

    def get_image(self, index):
        image_info = self.data[index]
        image = self._read_image(image_info['image_id'])
        if self.transform:
            image, _ = self.transform(image)
        return image

    def _getitem(self, index):
        image_info = self.data[index]
        image = self._read_image(image_info['image_id'])
        boxes = image_info['boxes']
        boxes[:, 0] *= image.shape[1]
        boxes[:, 1] *= image.shape[0]
        boxes[:, 2] *= image.shape[1]
        boxes[:, 3] *= image.shape[0]
        labels = image_info['labels']
        if self.transform:
            image, boxes, labels = self.transform(image, boxes, labels)
        if self.target_transform:
            boxes, labels = self.target_transform(boxes, labels)
        return image_info['image_id'], image, boxes, labels

    def __getitem__(self, index):
        _, image, boxes, labels = self._getitem(index)
        return image, boxes, labels

    def get_annotation(self, index):
        image_id, image, boxes, labels = self._getitem(index)
        is_difficult = np.zeros(boxes.shape[0], dtype=np.uint8)
        return image_id, (boxes, labels, is_difficult)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        if self.class_stat is None:
            self.class_stat = {name: 0 for name in self.class_names[1:]}
            for example in self.data:
                for class_index in example['labels']:
                    class_name = self.class_names[class_index]
                    self.class_stat[class_name] += 1
        content = ["Dataset Summary:"
                   f"Number of Images: {len(self.data)}",
                   f"Minimum Number of Images for a Class: {self.min_image_num}",
                   "Label Distribution:"]
        for class_name, num in self.class_stat.items():
            content.append(f"\t{class_name}: {num}")
        return "\n".join(content)