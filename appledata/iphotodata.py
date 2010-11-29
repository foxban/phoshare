'''iPhoto database: reads iPhoto database and parses it into albums and images.

@author: tsporkert@gmail.com

This class reads iPhoto image, event, album information from the file
AlbumData.xml in the iPhoto library directory. That file is written by iPhoto
for the media browser in other applications. All data are
organized in the class IPhotoData. Images in iPhoto are grouped using events
(formerly knows as rolls) and albums. Each image is in exactly one event, and
optionally, in zero or more albums. Albums can be nested (folders). The album
types are:
Flagged - flagged pictures
Folder - contains other albums
Published - an album published to MobileMe
Regular - a regular user created album
SelectedEventAlbum - most recent album (as shown in iPhoto)
Shelf - list of flagged images
Smart - a user created smart album
SpecialMonth - "Last Month"
SpecialRoll -  "Last Import"
Event - this type does not exist in the XML file, but we use it in this code
        to allow us to treat events just like any other album
Face - Face album (does not exist in iPhoto, only in this code).
None - should not really happen
'''

# Copyright 2010 Google Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import datetime
import os
import sys

import appledata.applexml as applexml
import tilutil.imageutils as imageutils
import tilutil.systemutils as sysutils

def parse_face_rectangle(string_data):
    """Parse a rectangle specification into an array of coordinate data.

       Args:
         string_data: Rectangle like '{{x, y}, {width, height}}'

       Returns:
         Array of x, y, width and height as floats.
    """
    try:
        return [float(entry.strip('{} ')) for entry in string_data.split(',')]
    except ValueError:
        print >> sys.stderr, 'Failed to parse rectangle ' + string_data
        return [ 0.4, 0.4, 0.2, 0.2 ]

class IPhotoData(object):
    """top level iPhoto data node."""

    def __init__(self, xml_data, is_aperture):
        """# call with results of readAppleXML."""
        self.data = xml_data
        self.aperture = is_aperture

        self.albums = {}
        self.face_albums = None

        # Master map of keywords
        self.keywords = self.data.get("List of Keywords")

        self.face_names = {}  # Master map of faces
        face_list = self.data.get("List of Faces")
        if face_list:
            for face_entry in face_list.values():
                face_key = face_entry.get("key")
                face_name = face_entry.get("name")
                self.face_names[face_key] = face_name
                # Other keys in face_entry: image, key image face index,
                # PhotoCount, Order

        self.images_by_id = {}
        image_data = self.data.get("Master Image List")
        if image_data:
            for key in image_data:
                image = IPhotoImage(image_data.get(key), self.keywords,
                                    self.face_names)
                self.images_by_id[key] = image

        album_data = self.data.get("List of Albums")

        self.root_album = IPhotoContainer("", "Root", None, None)
        for data in album_data:
            album = IPhotoAlbum(data, self.images_by_id, self.albums,
                                self.root_album)
            self.albums[album.albumid] = album

        roll_data = self.data.get("List of Rolls")
        self._rolls = {}
        if roll_data:
            for roll in roll_data:
                roll = IPhotoRoll(roll, self.images_by_id)
                self._rolls[roll.albumid] = roll
                self.root_album.addalbum(roll)

        self.images_by_base_name = None
        self.images_by_file_name = None

    def _build_image_name_list(self):
        self.images_by_base_name = {}
        self.images_by_file_name = {}

        # build the basename map
        for image in self.images_by_id.values():
            base_name = image.getbasename()
            other_images = self.images_by_base_name.get(base_name)
            if other_images is None:
                other_images = []
                self.images_by_base_name[base_name] = other_images
            other_images.append(image)

            imagename = image.getimagename()
            other_image_list = self.images_by_file_name.get(imagename)
            if other_image_list is None:
                other_image_list = []
                self.images_by_file_name[imagename] = other_image_list
            other_image_list.append(image)


    def _getapplicationversion(self):
        return self.data.get("Application Version")
    applicationVersion = property(_getapplicationversion, doc='iPhoto version')

    def _getimages(self):
        return self.images_by_id.values()
    images = property(_getimages, "List of images")

    def _getrolls(self):
        return self._rolls.values()
    rolls = property(_getrolls, "List of rolls (events)")

    def getroll(self, album_id):
        return self._rolls.get(album_id)    

    def getbaseimages(self, base_name):
        """returns an IPhotoImage list of all images with a matching base name.
        """
        if not self.images_by_base_name:
            self._build_image_name_list()
        return self.images_by_base_name.get(base_name)

    def getnamedimage(self, file_name):
        """returns an IPhotoImage for the given file name."""
        if not self.images_by_file_name:
            self._build_image_name_list()
        image_list = self.images_by_file_name.get(file_name)
        if image_list:
            return image_list[0]
        return None

    def getallimages(self):
        """returns map from full path name to image."""
        image_map = {}
        for image in self.images_by_id.values():
            image_map[image.GetImagePath()] = image
            image_map[image.thumbpath] = image
            if image.originalpath is not None:
                image_map[image.originalpath] = image
        return image_map

    def checkalbumsizes(self, max_size):
        """Prints a message for any event or album that has too many images."""
        messages = []
        for album in self._rolls.values():
            if album.size > max_size:
                messages.append("%s: event too large (%d)" % (album.name, 
                                                              album.size))
        for album in self.albums.values():
            if album.albumtype == "Regular" and album.size > max_size:
                messages.append("%s: album too large (%d)" % (album.name, 
                                                              album.size))
        messages.sort()
        for message in messages:
            print message


#  public void checkComments() {
#    TreeSet<String> images = new TreeSet<String>();
#    for (IPhotoImage image : images_by_id.values()) {
#      String comment = image.GetComment();
#      if ((comment == null or comment.length() == 0) && !image.IsHidden())
#        images.add(image.caption);
#    }
#    for (String caption : images)
#      System.out.println(caption + ": missing comment.");
#  }

    def check_inalbums(self):
        """Checks that all images are in albums according to their events."""
        messages = []
        for image in self.images_by_id.values():
            if image.IsHidden():
                continue
            roll_name = self._rolls[image.roll].name
            albums = []
            in_album = False

            for album in image.GetAlbums():
                album_name = album.name
                if album.GetAlbumType == "Regular":
                    albums.append(album.name)
                    in_album = True
                    if album_name != roll_name:
                        messages.append(image.caption + ": in wrong album (" +
                                        roll_name + " vs. " + album_name + ").")
                elif (album.isSmart() and album_name.endswith(" Collection") or
                      album_name == "People" or album_name == "Unorganized"):
                    in_album = True
            if not in_album:
                messages.append(image.caption + ": not in any album.")
            if albums:
                messages.append(image.caption + ": in more than one album: " +
                                " ".join(albums))
        messages.sort()
        for message in messages:
            print message

    def getfacealbums(self):
        """Returns a map of albums for faces."""
        if self.face_albums:
            return self.face_albums.values()

        # Build the albums on first call
        self.face_albums = {}

        for image in self.images:
            for face in image.getfaces():
                face_album = self.face_albums.get(face)
                if not face_album:
                    face_album = IPhotoFace(face)
                    self.face_albums[face] = face_album
                face_album.addimage(image)
        return self.face_albums.values()


class IPhotoImage(object):
    """Describes an image in the iPhoto database."""

    def __init__(self, data, keyword_map, face_map):
        self.data = data
        self._caption = sysutils.nn_string(data.get("Caption")).strip()
        self.comment = sysutils.nn_string(data.get("Comment")).strip()
        if data.has_key("DateAsTimerInterval"):
            self.date = applexml.getappletime(data.get("DateAsTimerInterval"))
        else:
            self.date = None
        self.mod_date = applexml.getappletime(
            data.get("ModDateAsTimerInterval"))
        self.image_path = data.get("ImagePath")
        if data.has_key("Rating"):
            self.rating = int(data.get("Rating"))
        else:
            self.rating = None
        if data.get("longitude"):
            latitude = float(data.get("latitude"))
            longitude = float(data.get("longitude"))
            self.gps = imageutils.GpsLocation(latitude, longitude)
        else:
            self.gps = None

        self.keywords = []
        keyword_list = data.get("Keywords")
        if keyword_list is not None:
            for i in keyword_list:
                self.keywords.append(keyword_map.get(i))

        self.originalpath = data.get("OriginalPath")
        self.roll = data.get("Roll")

        self.albums = []  # list of albums that this image belongs to
        self.faces = []
        self.face_rectangles = []

        face_list = data.get("Faces")
        if face_list:
            for face_entry in face_list:
                face_key = face_entry.get("face key")
                face_name = face_map.get(face_key)
                if face_name:
                    self.faces.append(face_name)
                    # Rectangle is '{{x, y}, {width, height}}' as ratios,
                    # referencing the lower left corner of the face rectangle.
                    self.face_rectangles.append(parse_face_rectangle(
                        face_entry.get("rectangle")))
                # Other keys in face_entry: face index

    def getimagepath(self):
        """Returns the full path to this image.."""
        return self.image_path

    def getimagename(self):
        """Returns the file name of this image.."""
        name = os.path.split(self.image_path)[1]
        return name

    def getbasename(self):
        """Returns the base name of the main image file."""
        return sysutils.getfilebasename(self.image_path)

    def _getcaption(self):
        if not self._caption:
            return self.getimagename()
        return self._caption
    caption = property(_getcaption, doc="Caption (title) of the image")

    def ismovie(self):
        """Tests if this image is a movie."""
        return self.data.get("MediaType") == "Movie"

    def addalbum(self, album):
        """Adds an album to the list of albums for this image."""
        self.albums.append(album)

    def addface(self, name):
        """Adds a face (name) to the list of faces for this image."""
        self.faces.append(name)

    def getfaces(self):
        """Gets the list of face tags for this image."""
        return self.faces

    def ishidden(self):
        """Tests if the image is hidden (using keyword "Hidden")"""
        return "Hidden" in self.keywords

    def _getthumbpath(self):
        return self.data.get("ThumbPath")
    thumbpath = property(_getthumbpath, doc="Path to thumbnail image")

    def _getrotationisonlyedit(self):
        return self.data.get("RotationIsOnlyEdit")
    rotation_is_only_edit = property(_getrotationisonlyedit,
                                     doc="Rotation is only edit.")


class IPhotoContainer(object):
    """Base class for IPhotoAlbum and IPhotoRoll."""

    def __init__(self, name, albumtype, data, images):
        self.name = name
        # The iPhoto master album has no album type.
        if not albumtype and name == 'Photos':
            albumtype = 'Master'
            
        # Convert Aperture numeric album types to iPhoto album type names.
        if albumtype == '1':
            albumtype = 'Regular'
        elif albumtype == '2':
            albumtype = 'Smart'
        elif albumtype == '3':
            albumtype = 'Special'
        elif albumtype == '4':
            albumtype = 'Event'
        elif albumtype == '5':
            albumtype = 'Library'
        elif albumtype == '6':
            albumtype = 'Folder'
        elif not albumtype:
            print 'No album type for %s.' % name
        elif albumtype.isdigit():
            albumid = int(albumtype)
            if albumid > 90:
                # 94 - Photos
                # 95 - Flagged
                # 96 - Library Album
                # 97 - Projects
                # 98 - Aperture
                # 99 - Aperture Library
                albumtype = name
            else:
                print 'Unknown album type %s for %s.' % (albumtype, name)
        self.albumtype = albumtype
        self.data = data

        self.albumid = -1
        self.images = []
        self.albums = []
        self.master = False

        if not self.isfolder() and data and data.has_key("KeyList"):
            keylist = data.get("KeyList")
            for key in keylist:
                image = images.get(key)
                if image:
                    self.images.append(image)
                else:
                    print "%s: image with id %s does not exist." % (name, key)

    def _getcomment(self):
        return self.data.get("Comments")
    comment = property(_getcomment, doc='comments (description)')

    def _getsize(self):
        return len(self.images)
    size = property(_getsize, "Gets the size (# of images) of this album.")

    def isfolder(self):
        """tests if this album is a folder."""
        return "Folder" == self.albumtype

    def getfolderhint(self):
        """Gets a suggested folder name from comments."""
        if self.comment:
            for comment in self.comment.split("\n"):
                if comment.startswith("@"):
                    return comment[1:]
        return None

    def getcommentwithouthints(self):
        """Gets the image comments, with any folder hint lines removed"""
        result = []
        if self.comment:
            for line in self.comment.split("\n"):
                if not line.startswith("@"):
                    result.append(line)
        return "\n".join(result)

    def addalbum(self, album):
        """adds an album to this container."""
        self.albums.append(album)

    def tostring(self):
        """Gets a string that describes this album or event."""
        return "%s (%s)" % (self.name, self.albumtype)


class IPhotoRoll(IPhotoContainer):
    """Describes an iPhoto Roll or Event."""

    def __init__(self, data, images):
        IPhotoContainer.__init__(self,
                                 data.get("RollName")
                                 if data.has_key("RollName")
                                 else data.get("AlbumName"),
                                 "Event", data, images)
        self.albumid = data.get("RollID")
        if not self.albumid:
            self.albumid = data.get("AlbumId")

    def _getdate(self):
        return applexml.getappletime(self.data.get("RollDateAsTimerInterval"))
    date = property(_getdate, doc="Date of event.")


class IPhotoAlbum(IPhotoContainer):
    """Describes an iPhoto Album."""

    def __init__(self, data, images, album_map, root_album):
        IPhotoContainer.__init__(self, data.get("AlbumName"),
                                 data.get("Album Type"),
                                 data, images)
        self.albumid = data.get("AlbumId")
        if data.has_key("Master"):
            self.master = True

        parent_id = data.get("Parent")
        if parent_id is None:
            self.parent = root_album
        else:
            self.parent = album_map.get(parent_id)
            if not self.parent:
                print "Album %s: parent with id %d not found." % (
                    self.name, parent_id)
        if self.parent:
            self.parent.addalbum(self)

        # Albums have no date attribute, so we calculate it from the image
        # dates.
        self.date = datetime.datetime.now()
        for image in self.images:
            if image.date and image.date < self.date:
                self.date = image.date

class IPhotoFace(object):
    """An IPhotoContainer compatible class for a face."""

    def __init__(self, face):
        self.name = face
        self.albumtype = "Face"
        self.albumid = -1
        self.images = []
        self.albums = []
        self.comment = ""

    def _getsize(self):
        return len(self.images)
    size = property(_getsize, "Gets the size (# of images) of this album.")

    def isfolder(self):
        """tests if this album is a folder."""
        return False

    def getfolderhint(self):
        """Gets a suggested folder name from comments."""
        return None

    def getcommentwithouthints(self):
        """Gets the image comments, with any folder hint lines removed"""
        return ""

    def addimage(self, image):
        """Adds an image to this container."""
        self.images.append(image)

    def tostring(self):
        """Gets a string that describes this album or event."""
        return "%s (%s)" % (self.name, self.albumtype)


def get_album_xmlfile(library_dir):
    """Locates the iPhoto AlbumData.xml or Aperture ApertureData.xml file."""
    if os.path.exists(library_dir) and os.path.isdir(library_dir):
        album_xml_file = os.path.join(library_dir, "AlbumData.xml")
        if os.path.exists(album_xml_file):
            return album_xml_file
        album_xml_file = os.path.join(library_dir, "ApertureData.xml")
        if os.path.exists(album_xml_file):
            return album_xml_file 
    raise ValueError, ("%s does not appear to be a valid iPhoto or Aperture "
                       "library location.") % (library_dir)


def get_iphoto_data(album_xml_file):
    """reads the iPhoto database and converts it into an iPhotoData object."""
    library_dir = os.path.dirname(album_xml_file)
    print "Reading iPhoto database from " + library_dir + "..."
    album_xml = applexml.read_applexml(album_xml_file)

    data = IPhotoData(album_xml, album_xml_file.endswith('ApertureData.xml'))
    if data.aperture:
        if not data.applicationVersion.startswith('3.'):
            raise ValueError, "Aperture version %s not supported" % (
                data.applicationVersion)
    else:
        if (not data.applicationVersion.startswith("9.") and
            not data.applicationVersion.startswith("8.") and
            not data.applicationVersion.startswith("7.") and
            not data.applicationVersion.startswith("6.")):
            raise ValueError, "iPhoto version %s not supported" % (
                data.applicationVersion)

    return data
