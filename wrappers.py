import enum
import ctypes
import os
from typing import Optional, Self

libc = ctypes.CDLL("./build/operations.so")

BLOCK_SIZE = 1024
NAME_MAX_LENGTH = 32
DIRECT_BLOCKS_COUNT = 12
DEFAULT_TEST_FILE_NAME = "temp_test_file"


SHORT_DATA = "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam"
# just some 1200 chars long data...
LONG_DATA = "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Duis autem vel eum iriure dolor in hendrerit in vulputate velit esse molestie consequat, vel illum dolore eu feugiat nulla facilisis at vero eros et accumsan et iusto odio dignissim qui blandit praesent luptatum zzril delenit augue duis dolore te feugait nulla facilisi. Lorem ipsum dolor sit amet, consectetue. "


# Define the node_type enumeration
class NodeType(enum.IntEnum):
    reg_file = 1
    directory = 2
    free_block = 3


# Define the data_block structure
class DataBlock(ctypes.Structure):
    _fields_ = [("size", ctypes.c_size_t), ("block", ctypes.c_uint8 * BLOCK_SIZE)]


# Define the inode structure
class Inode(ctypes.Structure):
    _fields_ = [
        ("n_type", ctypes.c_int),
        ("size", ctypes.c_uint16),
        ("name", ctypes.c_char * NAME_MAX_LENGTH),
        ("direct_blocks", ctypes.c_int * DIRECT_BLOCKS_COUNT),
        ("parent", ctypes.c_int),
    ]


# Define the superblock structure
class Superblock(ctypes.Structure):
    _fields_ = [("num_blocks", ctypes.c_uint32), ("free_blocks", ctypes.c_uint32)]


# Define the file_system structure
class FileSystem(ctypes.Structure):
    _fields_ = [
        ("s_block", ctypes.POINTER(Superblock)),
        ("free_list", ctypes.POINTER(ctypes.c_uint8)),
        ("inodes", ctypes.POINTER(Inode)),
        ("data_blocks", ctypes.POINTER(DataBlock)),
        ("root_node", ctypes.c_int),
    ]


# creates a new filesystem using the C-Function
def setup(fs_size):
    fsize = ctypes.c_int()
    try:
        fsize.value = fs_size
    except:
        fsize.value = 5

    creator = libc.fs_create
    creator.restype = ctypes.POINTER(FileSystem)
    ptr = creator(ctypes.c_char_p(bytes("./mypyfiles.fs", "UTF-8")), fsize)
    return ptr.contents


def set_dir(name: str, inode: int, parent: int, parent_block: int, fs):
    fs.inodes[inode].n_type = 2
    fs.inodes[inode].name = bytes(name, "utf-8")
    fs.inodes[inode].parent = parent
    fs.inodes[parent].direct_blocks[parent_block] = inode
    return fs


def set_fil(name: str, inode: int, parent: int, parent_block: int, fs):
    fs.inodes[inode].n_type = 1
    fs.inodes[inode].name = bytes(name, "utf-8")
    fs.inodes[inode].parent = parent
    fs.inodes[parent].direct_blocks[parent_block] = inode
    return fs


class TInode:
    """A wrapper for inodes to make writing unit tests easier"""

    idx: int | None
    name: str
    n_type: NodeType
    parent: int
    blocks: list[int]

    def __init__(
        self,
        fs: FileSystem,
        name: str,
        n_type: NodeType = NodeType.directory,
        parent: int = 0,
        idx: int | None = None,
        blocks: list[int] = [0] * 12,
    ):
        assert len(name) == 32
        self.name = name
        self.n_type = n_type
        assert parent > 0 and parent < fs.s_block[0].num_blocks
        assert fs.inodes[parent].n_type == NodeType.directory
        self.parent = parent
        assert len(blocks) <= DIRECT_BLOCKS_COUNT
        self.blocks = blocks + [-1] * (DIRECT_BLOCKS_COUNT - len(blocks))

        if idx is not None:
            assert idx > 0 and idx < fs.s_block[0].num_block
            self.idx = idx

    def __setitem__(self, key: str | int, value: int | str | NodeType):
        if key == "name":
            # names need to be strings
            assert isinstance(value, str) and len(value) <= NAME_MAX_LENGTH
            self.name = value
        elif key == "n_ntype":
            assert isinstance(value, (int, NodeType))
            self.n_type = NodeType(value)
        elif key == "parent":
            assert isinstance(value, int) and value > 0
            self.parent = value
        elif key == "idx":
            assert isinstance(value, int)
            self.pin(value)
        elif isinstance(key, int) and isinstance(value, int):
            assert value > 0
            self.blocks[key] = value
        else:
            raise KeyError(f"No applicable attribute for key '{key}' [{type(key)}] ('{value}' [{type(value)}]) found")

    def pin(self, idx: int):
        """Pins inode to specific inode idx for easier assertions"""
        assert idx > 0
        self.idx = idx

    def check(self, fs: FileSystem, idx: int | None = None, check_parents=True):
        """Assert all internal values against an fs node, this includes checking children for proper parent references"""
        # Ensure we have a defined way to reference an inode
        assert self.idx is not None or idx is not None

        if self.idx is None:
            self.idx = idx
        assert self.idx is not None
        assert self.idx > 0 and self.idx < fs.s_block[0].num_blocks

        # Get inode and compare attributes
        assert fs.inodes[self.idx].name.decode("utf-8") == self.name
        assert fs.inodes[self.idx].n_type == int(self.n_type)
        assert fs.inodes[self.idx].parent == self.parent

        if check_parents:
            # check all parents and direct block children
            assert any(
                fs.inodes[fs.inodes[self.idx].parent].direct_blocks[i] == self.idx for i in range(DIRECT_BLOCKS_COUNT)
            )
            assert all(
                map(
                    lambda block: fs.inodes[block].parent == self.idx,
                    map(lambda d: fs.inodes[self.idx].direct_blocks[d], range(DIRECT_BLOCKS_COUNT)),
                )
            )

        # compare the direct blocks to the internal representation
        assert all(fs.inodes[self.idx].direct_blocks[i] == self.blocks[i] for i in range(DIRECT_BLOCKS_COUNT))


def mkdir(fs, name: str, idx: int, parent: int, parent_direct_block: int | None = None) -> TInode:
    """Creates a directory at the specified inode idx"""

    inode = TInode(fs, name, NodeType.directory, parent, idx=idx)

    # If no parent block id was specified a new one will be found
    if parent_direct_block is None:
        assert parent > 0 and parent < fs.s_block[0].num_blocks

        for i in range(DIRECT_BLOCKS_COUNT):
            if fs.inodes[parent].direct_blocks[i] == -1:
                parent_direct_block = i
                break

        if parent_direct_block is None:
            raise LookupError("Failed to find an empty direct block in the parent")

    fs.inodes[idx].n_type = int(inode.n_type)
    fs.inodes[idx].name = bytes(inode.name, "utf-8")
    fs.inodes[idx].parent = parent
    fs.inodes[parent].direct_blocks[parent_direct_block] = inode.idx

    for i in range(DIRECT_BLOCKS_COUNT):
        fs.inodes[idx].direct_blocks[i] = inode.blocks[i]

    return inode


# set (overwrites) data block with abitrary data


# block_num addresses the location in thparent_blocke data_blocks array, whereas parent_block_num adresses the direct_blocks array in the parent inode
def set_data_block(block_num: int, data, data_size, parent_inode: int, parent_block_num: int, fs: FileSystem):
    if data_size > 1024:
        exit()
    fs.data_blocks[block_num].size = data_size

    for i in range(data_size):
        fs.data_blocks[block_num].block[i] = data[i]

    fs.inodes[parent_inode].direct_blocks[parent_block_num] = block_num

    # recalculate the total inode size
    fs.inodes[parent_inode].size = 0
    i = 0
    while True:
        if fs.inodes[parent_inode].direct_blocks[i] != -1:
            fs.inodes[parent_inode].size += fs.data_blocks[fs.inodes[parent_inode].direct_blocks[i]].size
            i += 1
        else:
            break
    fs.free_list[block_num] = 0
    fs.s_block[0].free_blocks = fs.s_block[0].free_blocks - 1

    return fs


# same as above, but only for strings
def set_data_block_with_string(block_num: int, string_data, parent_inode: int, parent_block_num: int, fs: FileSystem):
    string_data_block = [ord(i) for i in string_data]
    return set_data_block(
        block_num=block_num,
        data=string_data_block,
        data_size=len(string_data_block),
        parent_inode=parent_inode,
        parent_block_num=parent_block_num,
        fs=fs,
    )


def create_temp_file(data=SHORT_DATA, filename=DEFAULT_TEST_FILE_NAME):
    file = open(filename, "w")
    file.write(data)
    file.close
    return filename


def read_temp_file(filename=DEFAULT_TEST_FILE_NAME):
    return open(filename, "r").read()


def delete_temp_file(filename=DEFAULT_TEST_FILE_NAME):
    os.remove(filename)
