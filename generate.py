import sys
import re
import copy
import os
import shutil
import stat
import socket
import json

from contextlib import contextmanager
from pycparser import c_parser, c_ast, parse_file

#warning to python gurus. Ugly, goal-oriented, fiddly and improvised code.
class LibPS4Util:

    @staticmethod
    def copytree(src, dst, symlinks = False, ignore = None):
      if not os.path.exists(dst):
        LibPS4Util.makedirs(dst)
        shutil.copystat(src, dst)
      lst = os.listdir(src)
      if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]
      for item in lst:
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if symlinks and os.path.islink(s):
          if os.path.lexists(d):
            os.remove(d)
          os.symlink(os.readlink(s), d)
          try:
            st = os.lstat(s)
            mode = stat.S_IMODE(st.st_mode)
            os.lchmod(d, mode)
          except:
            pass # lchmod not available
        elif os.path.isdir(s):
          LibPS4Util.copytree(s, d, symlinks, ignore)
        else:
          shutil.copy2(s, d)

    @staticmethod
    def ignoreGitDir(src, lst):
        return [x for x in lst if '.git' in x]

    @staticmethod
    def ignoreBoilDirs(src, lst):
        return [x for x in lst if '.git' in x or 'LICENSE' in x or 'README.md' in x]

    @staticmethod
    def makedirs(dir):
        try:
            os.makedirs(dir)
        except:
            pass

    @staticmethod
    def touch(file): # does not actually perform "touch"
        if os.path.exists(file):
            return
        LibPS4Util.touchDirs(file)
        with open(file, 'a'):
            pass

    @staticmethod
    def walkFiles(dir):
        for root, dirs, files in os.walk(dir):
            for f in files:
                yield os.path.join(root, f)
            for d in dirs:
                LibPS4Util.walkFiles(os.path.join(root, d))

    @staticmethod
    def deepDictUpdate(d1, d2):
        for d in d2:
            if d in d1:
                if type(d2[d]) is dict:
                    LibPS4Util.deepDictUpdate(d1[d], d2[d])
                else:
                    d1[d] = d2[d]
            else:
                d1[d] = d2[d]

    @staticmethod
    def extractCIncludes(file):
        r = []
        with open(file, 'r') as f:
            for l in f:
                for i in re.findall('\#include [\<\"](.*)[\>\"]', l):
                    r.append(i)
        return r

    @staticmethod
    def extractSyscalls(file):
        r = {}
        with open(file, 'r') as f:
            for l in f:
                for s in re.findall('.*SYS_(.*)\t([0-9]*)', l):
                    r[s[0]] = s[1]
                if 'MAXSYSCALL' in r:
                    del r['MAXSYSCALL']
        return r

    @staticmethod
    def extractStaticModuleNames(file):
        r = {}
        with open(file, 'r') as f:
            for l in f:
                for m in re.findall('\#include [\<\"](.*)[\>\"]\t// as \[(.*)\]', l):
                    r[m[0]] = m[1]
        return r

    @staticmethod
    def moduleName(name):
        name = list(name.replace('.h', ''))
        name[0] = name[0].upper()
        r = []
        j = False
        for i in name:
            if j:
                r.append(i.upper())
                j = False
            elif i == '_':
                j = True
            else:
                r.append(i)
        return 'libSce' + ''.join(r) + '.sprx'

    @staticmethod
    def headerName(name):
        name = list(name.replace('libSce', '').replace('.sprx', ''))
        name[0] = name[0].lower()
        r = []
        for i in name:
            if i.isupper():
                i = "_" + i.lower()
            r.append(i)
        return ''.join(r) + '.h'

    @staticmethod
    def touchDirs(file):
        LibPS4Util.makedirs(file)
        shutil.rmtree(file, ignore_errors = True)

    @staticmethod
    def functionDeclarations(includeDir, includeFile):
        decls = {}

        if includeFile.endswith('in6.h'):
            return (decls, None)
        #print('<<<--- ' + includeFile)
        if '/ps4/' in includeFile:
            return (decls, None)

        args = \
        [
            r'-E',
            r'-w',
            r'-I' + includeDir,
            r'-nostdinc',
            r'-std=c11',
            r'-D_POSIX_C_SOURCE=200809',
            r'-D__ISO_C_VISIBLE=1999',
            r'-D__POSIX_VISIBLE=200809',
            r'-D__XSI_VISIBLE=700',
            r'-D__BSD_VISIBLE=1',
            r'-D_GNU_SOURCE=1',
            r'-D_DEFAULT_SOURCE=1',
            r'-D__ISO_C_VISIBLE=1999',
            r'-D_WITH_DPRINTF=1',
            r'-D_WITH_GETLINE=1',
            # From here on manual fixes for parsing various include files ...
            r'-Dlint',
            r'-D__builtin_va_list=int',
            r'-D__attribute__(...)=',
            r'-D__extension__(...)=',
            r'-D__format__(...)=',
            r'-D__typeof__(...)=',
            r'-D__asm__(...)=',
            r'-D__inline=',
            r'-D__volatile=',
            r'-D__asm(...)=',
            r'-Dvolatile(...)=',
            r'-Duintfptr_t=int',
            r'-Dintrmask_t=int',
            r'-Dsa_family_t=int',
            r'-D_SA_FAMILY_T_DECLARED',
            r'-DLIST_HEAD(...)=',
            r'-DLIST_ENTRY(...)=int',
            r'-DTAILQ_HEAD(...)=',
            r'-DTAILQ_ENTRY(...)=int',
            r'-DSLIST_HEAD(...)=',
            r'-DSLIST_ENTRY(...)=int',
            # Very specific fixes for missing includes or defines in some files ...
            #r'-includestdlib.h',
            #r'-includestdio.h',
            r'-includesys/cdefs.h',
            r'-includemachine/_types.h',
            r'-includesys/types.h',
            r'-includesys/_stdint.h',
            r'-includesys/elf.h',
            r'-includevm/vm.h',
            r'-includemachine/pmap.h',
            r'-includesys/lock.h',
            r'-D__ELF_WORD_SIZE=64',
        ]

        isKernel = False
        try:
            v = LibPS4FunctionDeclarationsVisitor(includeDir, decls)

            if not (includeFile.endswith('sockopt.h') or includeFile.endswith('eventvar.h')):
                ast = parse_file(includeFile, use_cpp=True,
                    cpp_path='gcc',
                    cpp_args=args
                )

                v.visit(ast)
                #ast.show()

            isKernel = True
            args.remove(r'-Duintfptr_t=int')
            args.remove(r'-Dintrmask_t=int')
            #args.remove(r'-Dsa_family_t=int')
            args.append(r'-D_KERNEL=1')
            args.append(r'-D_STANDALONE=1')
            ast = parse_file(includeFile, use_cpp=True,
                cpp_path='gcc',
                cpp_args=args
            )
            v.visit(ast)

        except Exception as e:
            print('isKernel ' + str(isKernel) + ' --->>> ' + includeFile)
            #print('--->>> ' + includeFile)
            #print(isKernel)
            print(e)
            p = 'gcc ' + includeFile + ' ' + ' '.join(args).replace(' -std=c11',' "-std=c11').replace(' -i', '" "-i').replace(' -D', '" -D"') + '"'
            print(p)
            print(os.popen(p).read())
            print('<<<--- ' + includeFile)
            (decls, e)

        return (decls, None)

class LibPS4FunctionDeclarationsVisitor(c_ast.NodeVisitor):

    def __init__(self, includeDir, decls):
        self.decls = decls
        self.includeDir = includeDir

    def visit_Decl(self, node):
        if type(node.type) == c_ast.FuncDecl:
            file, __ = str(node.coord).replace(self.includeDir, '').split(':')
            if file[0] == '/':
                file = file[1:]
            self.decls[node.name] = file

@contextmanager
def jsonFile(file, data = {}, access = 'rw'):
    access = set(list(access))
    if os.path.isfile(file) and 'r' in access:
        with open(file, 'r') as f:
            data = json.load(f)
    try:
        yield data
    finally:
        if 'w' in access:
            with open(file, 'w') as f:
                json.dump(data, f, indent=4, sort_keys=True)

#fix this properly ... eventually ... maybe ... meh ...
def jsonFile_(file, data = {}, access = 'rw'):
    with jsonFile(file, data, access):
        pass

class LibPS4Generator():

    def __init__(self, configFile = None):
        if configFile == None:
            configFile = os.path.abspath(os.path.join(os.path.realpath(__file__), '..', 'generate.conf'))

        with jsonFile(configFile, access = 'r') as data:
            self.config = data

        if not os.path.isabs(self.config['paths']['generator']):
            self.config['paths']['generator'] = \
                os.path.abspath(os.path.join(os.path.realpath(__file__), '..', self.config['paths']['generator']))

        for p in self.config['paths']:
            if not os.path.isabs(self.config['paths'][p]):
                self.config['paths'][p] = \
                    os.path.abspath(os.path.join(self.config['paths']['generator'], self.config['paths'][p]))

        self.staticModuleNames = LibPS4Util.extractStaticModuleNames(self.config['paths']['sceIndex'])
        self.staticHeaderNames = {v: k for k, v in self.staticModuleNames.items()}
        self.files = {'symbols': 'symbols.json'}
        for f in self.files:
            self.files[f] = os.path.join(self.config['paths']['generator'], 'data', self.files[f])
            LibPS4Util.touchDirs(self.files[f])

        setattr(self, 'import', self._import)

    def headerName(self, name):
        if name in self.staticHeaderNames:
            return self.staticHeaderNames[name]
        return LibPS4Util.headerName(name)

    def moduleName(self, name):
        if name in self.staticModuleNames:
            return self.staticModuleNames[name]
        return LibPS4Util.moduleName(name)

    def clean(self, where = None):
        w = ['include', 'source', 'stub', 'build', 'lib', 'Makefile', 'crt0.s', 'symbols.mk']
        if where in w:
            w = [where]
        for f in w:
            p = os.path.join(self.config['paths']['libps4'], f)
            shutil.rmtree(p, ignore_errors = True)
            try:
                os.remove(p)
            except:
                pass

    def cleanSelf(self):
        p = os.path.join(self.config['paths']['libps4'], 'data')
        shutil.rmtree(p, ignore_errors = True)

    def importFile(self, file, idir):
        dest = os.path.join(self.config['paths']['libps4'], 'include', file)
        src = os.path.join(idir, file)
        if os.path.exists(src) and not os.path.exists(dest):
            LibPS4Util.touchDirs(dest)
            shutil.copy(src, dest)
            os.chmod(dest, stat.S_IREAD | stat.S_IWRITE)
            self.importIncludes(file, idir)

    def importIncludes(self, file, idir):
        src = os.path.join(idir, file)
        for i in LibPS4Util.extractCIncludes(src):
            self.importFile(i, idir)

    def importStd(self):
        for i in LibPS4Util.extractCIncludes(self.config['paths']['stdIndex']):
            self.importFile(i, self.config['paths']['stdInclude'])

    def importSce(self):
        for i in LibPS4Util.extractCIncludes(self.config['paths']['sceIndex']):
            self.importFile(i, self.config['paths']['sceInclude'])

    def _import(self, what = 'all'):
        if what != 'sce' or what == 'all':
            self.importStd()
        if what != 'std' or what == 'all':
            self.importSce()

    def collect(self):
        decls = {}
        symbols = {}
        kernelSymbols = {}

        sceIncludes = set(LibPS4Util.extractCIncludes(self.config['paths']['sceIndex']))
        p = os.path.join(self.config['paths']['boilerplate'], 'include', 'sys', 'syscall.h')
        syscalls = LibPS4Util.extractSyscalls(p)

        inc = os.path.join(self.config['paths']['libps4'], 'include')
        for file in LibPS4Util.walkFiles(inc):
            ds, err = LibPS4Util.functionDeclarations(inc, file)
            LibPS4Util.deepDictUpdate(decls, ds)

        with jsonFile(self.config['paths']['kernelSymbols'], {}, 'r') as kernels:
            for kernelName in kernels:
                syms = kernels[kernelName]
                for symbolName in syms:
                    kernelSymbols[symbolName] = syms[symbolName]

        with jsonFile(self.config['paths']['symbolsAdd'], {}, 'r') as modules:
            for moduleName in modules:
                syms = modules[moduleName]
                for symbolName in syms:
                    decls[symbolName] = 'dummy.h'

        for d in decls:
            sys = None

            if d in syscalls:
                module = 'libkernel.sprx'
                sys = syscalls[d]
            else:
                module = 'libSceLibcInternal.sprx'

            kern = None
            if d in kernelSymbols and kernelSymbols[d] == 'function':
                kern = True
                #del kernelSymbols[d]

            if decls[d] in sceIncludes:
                module = self.moduleName(decls[d])

            if not module in symbols:
                symbols[module] = {}

            symbols[module][d] = {}
            if not sys is None:
                symbols[module][d]['syscall'] = sys
            if not kern is None:
                symbols[module][d]['kernel'] = kern
            symbols[module][d]['offset'] = None

        #symbols['kernel'] = []
        #for s in sorted(kernelSymbols.keys()):
        #    symbols['kernel'].append(s)

        jsonFile_(self.files['symbols'], symbols, 'w')

    def boil(self):
        LibPS4Util.copytree(self.config['paths']['boilerplate'], \
            self.config['paths']['libps4'], ignore=LibPS4Util.ignoreBoilDirs)

    def fake(self):
        with jsonFile(self.files['symbols'], {}) as modules:
            for moduleName in modules:
                symbols = modules[moduleName]
                for symbolName in symbols:
                    symbols[symbolName]['offset'] = 0

    def check(self):
        mods = {}
        with jsonFile(self.files['symbols'], {}) as modules:
            for moduleName in modules:
                #if moduleName == 'kernel':
                #    continue
                symbols = modules[moduleName]
                for symbolName in symbols:
                    symbol = symbols[symbolName]
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.connect((self.config['remote']['ip'], self.config['remote']['port']))
                        m = bytearray(moduleName + ' ' + symbolName, encoding='UTF-8')
                        m = m.ljust(128, b'\0')
                        sock.sendall(m)
                        res = sock.recv(128).decode(encoding='UTF-8').rstrip('\0')
                        module, symbol['offset'], found = res.split(' ')

                        if moduleName != module:
                            mods[symbolName] = symbol
                            symbol['guessed'] = moduleName
                            symbol['module'] = module
                        if found == '0':
                            symbol['offset'] = None

            for symbolName in mods:
                symbol = mods[symbolName]
                modules[symbol['module']][symbolName] = symbol
                del modules[symbol['guessed']][symbolName]
                del symbol['module']
                del symbol['guessed']

    def checkOrFake(self):
        try:
            self.check()
        except:
            self.fake()

    def generate(self):
        file = os.path.join(self.config['paths']['libps4'], 'symbols.mk')
        try:
            os.remove(file)
        except:
            pass

        out = {}
        kern = []
        sys = []
        syskern = []
        symout = 0
        symall = 0
        with jsonFile(self.files['symbols'], {}, 'r') as modules:
            for moduleName in modules:
                #if moduleName == 'kernel':
                #    kern = modules[moduleName]
                #    continue
                out[moduleName] = {}
                out[moduleName]['fun'] = []
                out[moduleName]['funsys'] = []
                out[moduleName]['funkern'] = []
                out[moduleName]['funsyskern'] = []
                out[moduleName]['kern'] = []
                out[moduleName]['sys'] = []
                out[moduleName]['syskern'] = []

                symbols = modules[moduleName]
                for symbolName in symbols:
                    symbol = symbols[symbolName]
                    symall += 1
                    s = ''
                    if 'offset' in symbol and not symbol['offset'] is None:
                        s += 'fun'
                    if 'syscall' in symbol:
                        s += 'sys'
                    if 'kernel' in symbol:
                        s += 'kern'
                    if s in out[moduleName]:
                        out[moduleName][s].append(symbolName)
                    else:
                        symout += 1

                out[moduleName]['module'] = moduleName.replace('.sprx', '')
                out[moduleName]['header'] = self.headerName(moduleName).replace('.h', '')

                out[moduleName]['fun'] = sorted(out[moduleName]['fun'])
                out[moduleName]['funsys'] = sorted(out[moduleName]['funsys'])
                out[moduleName]['funkern'] = sorted(out[moduleName]['funkern'])
                out[moduleName]['funsyskern'] = sorted(out[moduleName]['funsyskern'])

                kern.extend(out[moduleName]['kern'])
                sys.extend(out[moduleName]['sys'])
                syskern.extend(out[moduleName]['syskern'])
        print('Of ' + str(symall) + ' symbols, ' + str(symout) + ' where removed')

        with open(file, 'a') as f:
            for k in sorted(out.keys()):
                f.write('$(eval $(call generate, ' +
                    out[k]['module'] + ', ' +
                    out[k]['header'] + ', ' +
                    ' '.join(out[k]['fun']) + ', ' +
                    ' '.join(out[k]['funsys']) + ', ' +
                    ' '.join(out[k]['funkern']) + ', ' +
                    ' '.join(out[k]['funsyskern']) +
                    '))\n')
            f.write('$(eval $(call generateNonModule, syscall, ' + ' '.join(sys) + '))\n')
            f.write('$(eval $(call generateNonModule, kernelFunction, ' + ' '.join(kern) + '))\n')
            f.write('$(eval $(call generateNonModule, syscallAndKernelFunction, ' + ' '.join(syskern) + '))\n')

    def default(self):
        for act in self.config['default']:
            getattr(self, act)()

if __name__ == "__main__":

    if len(sys.argv) >= 2 and sys.argv[1] in ['clean', 'import', 'collect', \
        'check', 'fake', 'boil', 'generate', 'default']:
        getattr(LibPS4Generator(), sys.argv[1])(*sys.argv[2:])
    else:
        print('You must specify either:')
        print('clean [source|include]          # imported files')
        print('import <std|sce|all>            # FreeBSD or SCE module headers')
        print('collect                         # symbols in imported headers ')
        print('[check]                         # symbols on the PS4 (requires resolver and code exec)')
        print('[fake]                          # Poor mans check - mostly correct - some functions may not work')
        print('boil                            # copies base/ to source/ and include/')
        print('generate                        # source/ from include/')
        print('default                         # perform pre-configured actions')
