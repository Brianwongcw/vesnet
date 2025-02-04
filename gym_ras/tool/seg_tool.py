import json
import numpy as np
from pycocotools import mask
from skimage import measure
from pathlib import Path

def get_coco_category(cat_id, cat_name, supercategory_name = None):

    _dict =   {
      "id": cat_id,
      "name": cat_name,
    }
    if supercategory_name is not None:
        _dict["supercategory"] =  supercategory_name
    return _dict


def get_coco_image(image_id, file_dir, image_widith, image_height):
    _dir = Path(file_dir)
    return {
            "id": image_id,
            "file_name": _dir.name,
            "width": image_widith,
            "height": image_height
            }


def get_coco_annot(bool_arr, annot_id, image_id, category_id, iscrowd=False):
    ground_truth_binary_mask = bool_arr

    fortran_ground_truth_binary_mask = np.asfortranarray(ground_truth_binary_mask)
    encoded_ground_truth = mask.encode(fortran_ground_truth_binary_mask)
    ground_truth_area = mask.area(encoded_ground_truth)
    ground_truth_bounding_box = mask.toBbox(encoded_ground_truth)
    contours = measure.find_contours(ground_truth_binary_mask, 0.5)
    # print(contours)

    annotation = {
            "segmentation": [],
            "area": ground_truth_area.tolist(),
            "iscrowd": 1 if iscrowd else 0,
            "image_id": image_id,
            "bbox": ground_truth_bounding_box.tolist(),
            "category_id": category_id,
            "id": annot_id
        }

    for contour in contours:
        contour = np.flip(contour, axis=1)
        segmentation = contour.ravel().tolist()
        annotation["segmentation"].append(segmentation)

    return annotation

def generate_coco_json(images_list, annotations_list, categories_list, save_dir, save_file_name,
                         info_dict={}, licenses_list=[],):
# https://blog.csdn.net/hesongzefairy/article/details/104380405
    coco_json = {
    'info':info_dict,
    'licenses':licenses_list,
    'images':images_list,
    'annotations':annotations_list,
    'categories': categories_list,
        }
    _dir = Path(save_dir)
    _dir.mkdir(parents=True, exist_ok=True)
    _dir = _dir / (save_file_name + '.json')
    with open(str(_dir), "w") as file:
        json.dump(coco_json, file)


class DetectronPredictor():

    def __init__(self,
        cfg_dir,
        model_dir,
        save_anomaly=False,
    ):

        from detectron2.engine import DefaultPredictor
        from detectron2.config import get_cfg
        from detectron2 import model_zoo
        print("loading detectron model.....")
        # self.path = load_path or (model.__path__)[0]
        # self.path = Path(self.path)
        self.cfg = get_cfg()
        self.cfg.merge_from_file(cfg_dir)
        self.cfg.MODEL.WEIGHTS = model_dir
        # self.cfg.MODEL.ROI_HEADS.NUM_CLASSES = 2
        # self.cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5 # if 
        self.cfg.MODEL.DEVICE='cuda'
        # print(f"Segment_net model file: {self.cfg.MODEL.WEIGHTS}")
        self.predictor = DefaultPredictor(self.cfg)
        print("finish")
        self.is_save_anomaly_pic = save_anomaly
    def predict(self, rgb_arr):
        to_np = lambda x: x.detach().cpu().numpy()
        # start = time.time()
        result = self.predictor(rgb_arr)
        # print(result['instances'].pred_classes)
        # print(f"predict elapse time {time.time()-start}")
        masks = {}
    
        for j in range(result['instances'].pred_classes.shape[0]):
            _class_id = int(to_np(result['instances'].pred_classes[j]))
            # print(_class_id)
            # print(masks)
            if _class_id in masks:
                # if masks[_class_id][1] < to_np(result['instances'].scores[j]):
                masks[_class_id] = (to_np(result['instances'].pred_masks[j]) | masks[_class_id][0], 
                                    min(to_np(result['instances'].scores[j]), masks[_class_id][1]),
                                    )
            else:
                masks[_class_id] = (to_np(result['instances'].pred_masks[j]), 
                                    to_np(result['instances'].scores[j]))      
        # out = result['instances'].pred_masks.detach().cpu().numpy()
        # masks = [out[i,:,:] for i in range(out.shape[0])]
        # is_sucess = len(masks.keys())  ==2 # stop if score is less than set threshold, need more label data for training
        # print(masks)
        return masks
        # if len(masks.keys())==2:
        #     return masks, True 
        # else: # fail
        #     if self.is_save_anomaly_pic and float(time.time()-self.current_time) > 0.5:
        #         self.current_time = time.time()
        #         _anomaly_pic_path = Path(self.anomaly_pic_path) / self.robot_type 
        #         _anomaly_pic_path.mkdir(parents=True, exist_ok=True)
        #         _file =  "anomaly_" + time.strftime("%Y%m%d-%H%M%S") + ".png"
        #         cv2.imwrite(str(_anomaly_pic_path / _file), cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR))
        #     return None, False








############### here are simple coco example
# {
#   "images": [
#     {
#       "id": 1,
#       "file_name": "image1.jpg",
#       "width": 640,
#       "height": 480
#     },
#     {
#       "id": 2,
#       "file_name": "image2.jpg",
#       "width": 800,
#       "height": 600
#     }
#   ],
#   "annotations": [
#     {
#       "id": 1,
#       "image_id": 1,
#       "category_id": 1,
#       "segmentation": [[x1, y1, x2, y2, ...]],
#       "area": 1234,
#       "bbox": [x, y, width, height],
#       "iscrowd": 0
#     },
#     {
#       "id": 2,
#       "image_id": 1,
#       "category_id": 2,
#       "segmentation": [[x1, y1, x2, y2, ...]],
#       "area": 567,
#       "bbox": [x, y, width, height],
#       "iscrowd": 0
#     }
#   ],
#   "categories": [
#     {
#       "id": 1,
#       "name": "person",
#       "supercategory": "human"
#     },
#     {
#       "id": 2,
#       "name": "car",
#       "supercategory": "vehicle"
#     }
#   ],
#   "info": {
#     "description": "COCO 2017 dataset",
#     "version": "1.0",
#     "year": 2017,
#     "contributor": "Microsoft COCO group",
#     "url": "http://cocodataset.org"
#   },
#   "licenses": [
#     {
#       "id": 1,
#       "name": "CC BY-SA 2.0",
#       "url": "https://creativecommons.org/licenses/by-sa/2.0/"
#     }
#   ]
# }

