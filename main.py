import os
import sys
import getopt

from dfvfs.lib import definitions
from dfvfs.path import factory as path_spec_factory
from dfvfs.resolver import resolver as path_spec_resolver
from PIL import Image, ImageChops
import traceback
from io import BytesIO
import numpy as np


def img_similarity_check(img1, img2, similarity_threshold):
    """
    Function to check whether two images are similar or not
    :param similarity_threshold: threshold is adjustable for different algos
    :param img1: PIL.Image.open() processed image1
    :param img2: PIL.Image.open() processed image2
    :return: True if they are similar False otherwise
    """

    # pixel by pixel comparison
    diff = ImageChops.difference(img2, img1)
    diff_array = np.array(diff)
    mean_diff = np.mean(diff_array)

    is_similar = mean_diff < similarity_threshold

    return is_similar, mean_diff


def find_similar_images(disk_img_path, reference_image_folder_path, similarity_threshold, result, output_folder):
    """
    Function to compare input image and all images in the target disk image
    :param disk_img_path:  the path of disk image
    :param reference_image_folder_path: the folder path of compared images
    :param similarity_threshold: threshold is adjustable for different algos
    :param result: a dict storing result
    :param output_folder: optional output folder path
    :return: None
    """
    # Reference: https://dfvfs.readthedocs.io/en/latest/sources/Path-specifications.html
    os_image_path_spec = path_spec_factory.Factory.NewPathSpec(
        definitions.TYPE_INDICATOR_OS, location=disk_img_path)

    # indicates raw image type
    raw_image_path_spec = path_spec_factory.Factory.NewPathSpec(
        definitions.TYPE_INDICATOR_RAW, parent=os_image_path_spec)

    # indicates SleuthKit file system type
    file_system_path_spec = path_spec_factory.Factory.NewPathSpec(
        definitions.TYPE_INDICATOR_TSK, location='/',
        parent=raw_image_path_spec)

    file_system = path_spec_resolver.Resolver.OpenFileSystem(file_system_path_spec)
    print("File system parse completed.")

    # loading reference images in the folder
    reference_image_list = {}

    try:
        for filename in os.listdir(reference_image_folder_path):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff')):
                file_path = os.path.join(reference_image_folder_path, filename)
                image = Image.open(file_path)
                reference_image_list[file_path] = image
                result[file_path] = []

    except Exception as e:
        print(f"Error while loading image: ")
        print(f"Error Details: {e}")
        print(traceback.format_exc())
        return False

    print("Reference images loading completed.")

    # load file system
    root_file_entry = file_system.GetRootFileEntry()
    print("Disk root directory loading completed.")
    print("Start scanning similar images on the disk image - it may take a long time depending on the size of disk.")

    # recursively find similar images in the disk image
    traverse_file_entries(root_file_entry, reference_image_list, similarity_threshold, result, output_folder)


def is_image_similar(file_entry, reference_image_list, similarity_threshold, result, output_folder):
    """
    Given a single file and an image to judge whether they are similar
    :param file_entry: single file_entry (path_spec_resolver.Resolver.OpenFileSystem)
    :param reference_image_list: a dict of PIL.Image.open() processed images
    :param similarity_threshold: threshold is adjustable for different algos
    :param result: a dict storing result
    :param output_folder: optional output folder path
    :return: None but print similar img's path if found
    """
    try:
        # check file extension
        file_ext = os.path.splitext(file_entry.path_spec.location)[1].lower()
        valid_image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']

        if file_ext not in valid_image_extensions:
            return False

        file_object = file_entry.GetFileObject()
        if not file_object:
            return False
        file_content = file_object.read()

        file_content_io = BytesIO(file_content)
        image = Image.open(file_content_io)

        # check the current file with all reference images
        for reference_name, reference_image in reference_image_list.items():
            is_similar, mean_diff = img_similarity_check(image, reference_image, similarity_threshold)

            # similar image found
            if is_similar:
                res_tuple = (file_entry.path_spec.location, mean_diff)
                result[reference_name].append(res_tuple)
                print("Similar image identified! - See final report")
                if output_folder != "":
                    output_file_path = os.path.join(output_folder, file_entry.name)
                    image.save(output_file_path)

    except Exception as e:
        print(f"Error while comparing image: {file_entry.path_spec.location}")
        print(f"Error Details: {e}")
        print(traceback.format_exc())
        return False


def traverse_file_entries(file_entry, reference_image_list, similarity_threshold, result, output_folder):
    """
    Recursive method to find similar images against reference_img
    :param file_entry: file entry - could be dict or file
    :param reference_image_list: a dict of PIL.Image.open() processed images
    :param similarity_threshold: threshold is adjustable for different algos
    :param result: a dict storing result
    :param output_folder: optional output folder path
    :return: None
    """
    if not file_entry.IsDirectory():
        is_image_similar(file_entry, reference_image_list, similarity_threshold, result, output_folder)
    else:
        for sub_file_entry in file_entry.sub_file_entries:
            traverse_file_entries(sub_file_entry, reference_image_list, similarity_threshold, result, output_folder)


def print_usage():
    """
    print usage
    :return: None
    """
    print(
        f"Usage: {sys.argv[0]} -d <disk_image_path> -r <reference_image_folder> -i [optional threshold default = 10] "
        f"-o [optional output folder]")


if __name__ == '__main__':
    disk_image_path = ""
    reference_image_folder_path = ""
    similarity_threshold = 10
    output_folder = ""

    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hd:r:i:o:")
    except getopt.GetoptError:
        print_usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_usage()
            sys.exit()
        elif opt in ("-d"):
            disk_image_path = arg
        elif opt in ("-r"):
            reference_image_folder_path = arg
        elif opt in ("-i"):
            similarity_threshold = int(arg)
        elif opt in ("-o"):
            output_folder = arg
            try:
                os.makedirs(output_folder, exist_ok=True)
            except OSError as e:
                raise RuntimeError(f"Failed to create the output directory: {str(e)}")

    if not disk_image_path or not reference_image_folder_path:
        print("missing required parameters.")
        print_usage()
        sys.exit(2)

    # key: reference images path, value: list of tuple of (similar images' paths, difference)
    result = {}

    # find similar images
    find_similar_images(disk_image_path, reference_image_folder_path, similarity_threshold, result, output_folder)

    if len(result) != 0:
        print("Final Report: ")
    else:
        print("No similar images identified. Try to adjust threshold or add more reference images.")

    # print out final results
    for reference_image_name, similar_images in result.items():
        if len(similar_images) != 0:
            print(f"For reference Image {reference_image_name}: ")
            for stat in similar_images:
                print(f"\t{stat[0]:<80} \t\t difference: {stat[1]}")
