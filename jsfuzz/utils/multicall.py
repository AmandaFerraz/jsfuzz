import shlex, os, hashlib, ntpath, logging
from subprocess import STDOUT, check_output, PIPE, CalledProcessError, TimeoutExpired, getstatusoutput
from difflib import SequenceMatcher as matcher
from tempfile import mkstemp

from jsfuzz.utils import constants
from jsfuzz.fuzzer import radamsa_fuzzer
from jsfuzz.utils.blacklist import INVALID_STRINGS, ENGINES_KEYWORDS, REPORT_PASS_KEYWORDS, GLOBAL_HASH

'''
    Class that saves state across several multicalls
'''


class Multicalls:

    def __init__(self, long_file, short_file):
        self.numskipped = 0
        self.hashmap = {}
        self.hits = 0
        self.numfiles = 0
        self.numwarnings = 0
        self.long_file = long_file
        self.short_file = short_file

    def notify(self, res):
        ''' 
            This function will be called multiple times. Statistics will 
            be collected for these calls.
        ''' 
        self.numfiles += 1
        is_interesting_and_distinct = False
        if res.is_interesting(): # interesting if we find diverging responses
            self.numwarnings += 1
            hashcode = res.hash()
            if hashcode in self.hashmap:
                self.hits += 1
                tests = self.hashmap[hashcode]
            else:
                is_interesting_and_distinct = True
                self.hashmap[hashcode] = tests = set()
            tests.add(res)
            self.long_file.write(str(res))
            
            # all files with high priority is interesting
            if (res.priority() == '[HIGH]'):
                is_interesting_and_distinct = True
        elif res.is_invalid():
            self.numskipped += 1
        return is_interesting_and_distinct

    def save_summary(self):
        # generating log
        self.short_file.write('number of files processed: {}\n'.format(self.numfiles))
        self.short_file.write('number of warnings (interesting cases) observed: {}\n'.format(self.numwarnings))
        self.short_file.write('number of invalid cases observed: {}\n'.format(self.numskipped))
        self.short_file.write('number of cache hits: {}\n'.format(self.hits))
        self.short_file.write('number of buckets: {}\n'.format(len(self.hashmap)))
        # show contents associated with each bucket        
        bucket_num = 0
        for key, val_set in self.hashmap.items():
            bucket_num += 1
            self.short_file.write('\n>>>>>\n files in bucket #{}:\n'.format(bucket_num))
            bucket_files = []
            for res in val_set:
                if res.path_name in bucket_files:
                    continue
                cp_file = ' (copied)' if os.path.isfile(res.path_name) else ''
                self.short_file.write(' {}{}\n'.format(res.path_name, cp_file))
                bucket_files.append(res.path_name)

            if key not in GLOBAL_HASH:
                GLOBAL_HASH.append(key)
                self.short_file.write('\nhash: {}\n'.format(key))
            else:
                self.short_file.write('\nhash: {} (cached)\n'.format(key))

            res = next(iter(val_set))
            self.short_file.write('\npriority: {}\n'.format(res.priority()))
            self.short_file.write('\npattern:\n')
            self.short_file.write(res.str_canonical())


def multicall_directories(path_name, should_fuzz, validator=None, libs=None, search_root=None, search_libfiles=[], ignored_files=[]):
    """
        Process files in a directory, running multicall on each file.

        TODO: describe other params (if you decide to explain validator) -Marcelo

        :param search_libfiles: Names of library files that should be included if found in the folders between path_name
               and search_root.
        :param search_root: Topmost folder that should be searched for files listed in search_libfiles.
        :param libs: List with path to files that should be included
        :param callable validator: Function used to exclude files (e.g. parsing error). Calling the function on a valid
        file should return None/empty string; otherwise the reason for the error should be returned as a string.

    """
    if not os.path.exists(path_name):
        raise Exception('Cannot search *.js files in {}. Path does not exists.'.format(path_name))
    
    path_list = path_name.split('/')
    index = path_list.index('seeds') + 1
    name = 'fuzzed_' + '_'.join(path_list[index:])

    log_name_suffix = ('fuzz' if should_fuzz else '') + '_diff_report_' + name + '.txt'

    if not os.path.isdir(constants.logs_dir):
        os.mkdir(constants.logs_dir)

    short_log_path = os.path.join(constants.logs_dir, 'short' + log_name_suffix)
    long_log_path = os.path.join(constants.logs_dir, 'long' + log_name_suffix)
    
    with open(short_log_path, 'w') as short_file, open(long_log_path, 'w') as long_file:
        mcalls = Multicalls(long_file, short_file) 

        # search for js files recursively in directory path name
        for basename, file_path in [(f, os.path.join(dp, f)) for dp, dn, fn in os.walk(path_name) for f in sorted(fn) if f.endswith(".js")]:

            # skip library files and files that we declare to ignore
            if basename in search_libfiles or basename in ignored_files:
                continue

            # look for libraries necessary to spawn 
            if libs is None:
                libs = []

            test_specific_libs = []
            if search_root:
                search_root = os.path.abspath(search_root) #remove any '..' or '.'
                if search_libfiles:
                    current_dir = os.path.abspath(os.path.dirname(file_path))
                    while current_dir.startswith(search_root):
                        local_libs = [os.path.join(current_dir, f) for f in os.listdir(current_dir) if f in search_libfiles]
                        test_specific_libs = local_libs + test_specific_libs # not efficient, but not gonna use a deque here for now
                        current_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

            if should_fuzz:
                #pylint: disable=W0612
                try:
                    radamsa_fuzzer.fuzz_file(constants.num_iterations, file_path, mcalls, validator, libs=(libs + test_specific_libs))
                except Exception as e: # error raised by timeout decorator
                    logging.error('UNEXPECTED')
                    continue
            else:
                res = callAll(file_path, libs = (libs + test_specific_libs))
                mcalls.notify(res)

        mcalls.save_summary()


def callAll(pathName, validator=None, libs=None):
    '''
        This function calls all engines and returns a Results object (see class below) 
        encapsulating the output and error streams of corresponding calls
    '''
    res = Results(pathName) if not validator else Results(pathName, validator(pathName))
    
    # JavaScriptCore
    outerr = callJavaScriptCore(pathName, libs)    
    res.set_jsc_results(outerr)
    # Chakra
    outerr = callChakra(pathName, libs)
    res.set_chakra_results(outerr)
    # SpiderMonkey
    outerr = callSpiderMonkey(pathName, libs)
    res.set_spiderm_results(outerr)
    # v8
    outerr = callV8(pathName, libs)
    res.set_v8_results(outerr)

    return res

#TODO: see issue #16
def callJSEngine(cmd_line):
    '''
        This function makes the system call to the JS engine binary
    '''
    timeout_limit = constants.timeout_JS_engine
    cmd = shlex.split(cmd_line)
    msg = ''
    #pylint: disable=W0612
    try:
        msg = check_output(cmd, stderr=STDOUT, timeout=timeout_limit).decode('utf-8')
    except CalledProcessError as errorExc:
        msg = errorExc.output.decode('utf-8')
    except TimeoutExpired as timeoutExc:
        msg = 'Error: TIMEOUT'

    if not msg:
        # double check to get unexpected behaviour
        status, error = getstatusoutput(cmd_line)
        if error:
            msg = '[CHECK_MANUALLY] {}'.format(error)
    
    return msg

def callJavaScriptCore(pathName, libs=[]):
    if is_file_invalid('jscore', pathName):
        return 'FeatureError: File with feature not implemented yet'
    libcmd = " ".join(libs) if libs else ""
    cmd_line = constants.javascriptcore + " " + libcmd + " " + pathName
    #os.environ['LD_LIBRARY_PATH'] = constants.javascriptcore_lib_dir
    return callJSEngine(cmd_line)


# seems chakra only supports a single source file as input
def callChakra(path_name, libs=[]):
    if is_file_invalid('chakra', path_name):
        return 'FeatureError: File with feature not implemented yet'

    if libs and len(libs) > 0:
        fd, tmp_path = mkstemp(prefix="chakrafuzz", text=True)
        all_files = []
        all_files.extend(libs)
        all_files.append(path_name)
        with open(fd, 'w') as outfile:
            for filename in all_files:
                with open(filename) as infile:
                    outfile.write(infile.read())
                    outfile.write("\n\n")
        path_name = tmp_path

    cmd_line = constants.chakra + " " + path_name
    return callJSEngine(cmd_line)

def callSpiderMonkey(pathName, libs=[]):
    if is_file_invalid('spidermonkey', pathName):
        return 'FeatureError: File with feature not implemented yet'
    libcmd = (" -f " + " -f ".join(libs)) if libs else ""
    cmd_line = constants.spidermonkey + libcmd + " " + pathName
    return callJSEngine(cmd_line)

def callV8(pathName, libs=[]):
    if is_file_invalid('v8', pathName):
        return 'FeatureError: File with feature not implemented yet'
    libcmd = " ".join(libs) if libs else ""
    cmd_line = constants.v8 + " " + libcmd + " " + pathName
    return callJSEngine(cmd_line)

def is_file_invalid(engine, pathName):
    """
    Return True if file contains invalid code otherwise False
    """
    if engine not in ENGINES_KEYWORDS.keys():
        raise Exception('Engine not found. Only supported: {}'.format(ENGINES_KEYWORDS.keys()))
    
    if not ENGINES_KEYWORDS[engine]:
        return False

    with open(pathName) as js_file:
        file_raw = js_file.read()
        for keyword in ENGINES_KEYWORDS[engine]:
            if keyword in file_raw:
                return True
    return False

class Results:
    """
        An object of this class encapsulates the results of multiple
        calls to JS engines. It is used, for example, to check if
        there is observed discrepancies across calls.
    """

    def __init__(self, path_name, validation_error=None):
        self.path_name = path_name
        self.validation_error = validation_error

    def __str__(self):
        if self.validation_error:
            return "***  {path}\n    validation error: {error}\n".format(path=self.path_name,error=self.validation_error)
        else:
            return ("***  " + self.path_name + "\n" 
            "-------------JavaScriptCore\n" +
            self.jsc_outerr + "\n" +
            "-------------Chakra\n" +
            self.chakra_outerr + "\n" +
            "-------------SpiderMonkey\n" +
            self.spiderm_outerr + "\n" +
            "-------------v8\n" +
            self.v8_outerr + "\n")

    '''
        This string function abstract the parts of error messages 
        related to the code that originated the error. This is 
        important to identify duplicate errors.
    '''
    def str_canonical(self):
        if self.validation_error:
            return self.validation_error
        else:
            return (
            "-------------JavaScriptCore\n" +
            self.abstract(self.jsc_outerr) + "\n" +
            "-------------Chakra\n" +
            self.abstract(self.chakra_outerr) + "\n" +
            "-------------SpiderMonkey\n" +
            self.abstract(self.spiderm_outerr) + "\n" +
            "-------------v8\n" +
            self.abstract(self.v8_outerr) + "\n")

    def abstract(self, string):
        error_message = ''
        for line in string.splitlines():
            if [invalid for invalid in REPORT_PASS_KEYWORDS if invalid in line]:
                break
            
            elif 'Error' in line:
                ind = line.index('Error')
                error_message = line[ind:] if 'Error' in line[ind:] else line
                break
            
            elif 'Fatal' in line:
                ind = string.index('Fatal')
                error_message = string[ind:]
                break

        return error_message

    def hash(self):
        bytes = self.str_canonical().encode()
        hash_object = hashlib.md5(bytes)
        return hash_object.hexdigest()

    def priority(self):
        """
        Define priority based on engine output
        """
        priority = None
                
        # set low priority if only chakra reports/not reports an error
        at_least = any([self.jsc_outerr, self.v8_outerr, self.spiderm_outerr])
        only_chakra_reports = self.chakra_outerr and not at_least
        only_chakra_not_reports = not self.chakra_outerr and all([self.jsc_outerr, self.v8_outerr, self.spiderm_outerr])
        is_low_priority = (only_chakra_reports or only_chakra_not_reports)

        if self.is_high_priority():
            priority = '[HIGH]'
        elif is_low_priority:
            priority = '[LOW]'
        else:
            priority = '[MEDIUM]'
        
        return priority

    def is_high_priority(self):
        '''
            Check if a string is a warning with HIGH priority.
            We based on pattern on textual reports
        '''
        # TODO: update textual patterns that is considered high priority
        patterns = [
            'test failed', 'fatal', 'assertion failed', 'failed!',
            'attempting to', 'do not match expectation', 'requires',
            'jsfuzz error', 'bad result', 'Type error'
        ]

        for output in self.get_all_outerr():
            out = output.lower()
            for pattern in patterns:
                # using ratio of equivalence because fuzzer can alter N chars in a string
                if (pattern in out) or \
                    (matcher(None, pattern, out).ratio() >= 0.6):
                    return True
        return False

    def is_interesting(self):
        '''
            This is the function that decides whether or not this result is 
            interesting and should be reported.
        '''
        try:
            all_engines = all(self.get_all_outerr())
            is_fundamentally_interesting = self.is_valid() and self.is_atleastone() and not all_engines
            if not (is_fundamentally_interesting): ## necessary condition to be interesting
                return False
            
            return not self.is_spurious()
        
        except AttributeError:  # TODO either add all missing attr. to the (invalidated) result or fix this
            return False

    def is_spurious(self):
        """
        Remove spurious reports based on keywords/strings
        TODO: updating strings in blacklist file
        """
        ## TODO: Igor, why only Chakra raises undefined/not defined? - Marcelo
        ## Chakra is a new engine, some features are not implemented yet
       
        all_outputs = self.get_all_outerr()
        for engine_output in all_outputs:
            if 'Fatal' in engine_output or '[CHECK_MANUALLY]' in engine_output:
                return False

        # TODO: check better solution
        for engine_output in all_outputs:
            for keyword in INVALID_STRINGS:
                keyword = keyword.lower()
                if keyword in engine_output.lower():
                    return True
        return False

    def is_invalid(self):
        return self.validation_error

    def is_valid(self):
        return self.validation_error is None

    def is_atleastone(self):
        """
        Return True if at least one engine reports an error message
        """
        return any(self.get_all_outerr())
    
    def get_all_outerr(self):
        """
        Return a list of all engines output errors
        """
        return [
            self.abstract(self.jsc_outerr),
            self.abstract(self.chakra_outerr),
            self.abstract(self.spiderm_outerr),
            self.abstract(self.v8_outerr)
        ]


    # TODO generalize this stuff with a dict

    def set_jsc_results(self, outerr):
        self.jsc_outerr = outerr if not self.validation_error else None

    def set_chakra_results(self, outerr):
        self.chakra_outerr = outerr if not self.validation_error else None

    def set_spiderm_results(self, outerr):
        self.spiderm_outerr = outerr if not self.validation_error else None

    def set_v8_results(self, outerr):
        self.v8_outerr = outerr if not self.validation_error else None
    

if __name__ == "__main__":
    # example
    res = callAll(os.path.join(constants.seeds_dir, 'max.js'))
    print (res)
