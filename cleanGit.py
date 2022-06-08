import os


def deleteFolder(folder):
    names = os.listdir(folder)
    for name in names:
        absPath = os.path.join(folder, name)
        if os.path.isfile(absPath):
            print('remove:', absPath)
            os.remove(absPath)
        else:
            deleteFolder(absPath)
    os.rmdir(folder)


def deleteGit(folder):
    names = os.listdir(folder)
    for name in names:
        absPath = os.path.join(folder, name)
        if os.path.isfile(absPath):
            continue
        if name != '.git':
            deleteGit(absPath)
        else:
            deleteFolder(absPath)
            print("delete .git:", absPath)


print(__name__)

if __name__ == '__main__':
    cwd = os.getcwd()
    folder = os.path.join(cwd, 'third_party')
    print(folder)
    deleteGit(folder)
