from subprocess import Popen, PIPE
from argparse import ArgumentParser, Namespace
from concurrent.futures import ThreadPoolExecutor
import csv

ENCODING: str = "utf-8"
NO_ERROR: str = ""
RED: str = "\033[31m"
GREEN: str = "\033[32m"
RESET: str = "\033[0m"
STABLE_BRANCH_NAME: str = "autotest-stable"
error_list: dict[str, [str]] = {}
largest_message = 0
# Some notes. This script has been designed to be as defensive as possible to stop the merge process the moment an issue
# has been found.
verbose: bool


class UnknownGitException(Exception):
    def __init__(self, message: str):
        self.message = message


class Data:
    _repository: str
    _url: str
    _hashcode: str

    def __init__(self, repo: str, url: str, hashcode: str):
        self._repository = repo
        self._url = url
        self._hashcode = hashcode

    def get_url(self):
        return self._url

    def get_repository(self):
        return self._repository

    def get_hashcode(self):
        return self._hashcode


class Error:
    _message: str
    _is_error: bool

    def __init__(self, message: bytes, code: int):
        self._message = message.decode(ENCODING).replace("\n", "") if message else ""
        self._is_error = code != 0

    def get_message(self):
        return self._message

    def is_error(self):
        return self._is_error


def branch_exists(repository: str, branch_name: str) -> bool:
    cmd: Popen = Popen(["git", "branch", "-a"],
                       shell=True, cwd=f"./stable_workspace/{repository}/", stdout=PIPE)
    out, err = cmd.communicate()
    if err:
        raise UnknownGitException(f"Issue while checking branch error: {err.decode(ENCODING)}")
    out = out.decode(ENCODING)
    return branch_name in out


def clone(repository: str, url: str) -> bool:
    cmd: Popen = Popen(["git", "clone", url],
                       shell=True, cwd=f"./stable_workspace/", stdout=PIPE, stderr=PIPE)
    out, err = cmd.communicate()
    error: Error = Error(err, cmd.returncode)
    store_error(repository, error)
    return error.is_error()


def checkout_branch(repository: str, branch_name: str) -> bool:
    cmd: Popen = Popen(["git", "checkout", branch_name],
                       shell=True, cwd=f"./stable_workspace/{repository}/", stdout=PIPE, stderr=PIPE)
    out, err = cmd.communicate()
    error: Error = Error(err, cmd.returncode)
    store_error(repository, error)
    return error.is_error()


def create_branch_from_position(repository: str, branch_name: str):
    cmd: Popen = Popen(["git", "checkout", "-b", branch_name],
                       shell=True, cwd=f"./stable_workspace/{repository}/", stdout=PIPE)
    out, err = cmd.communicate()
    if cmd.returncode != 0:
        error: Error = Error(err, cmd.returncode)
    else:
        error: Error = Error("Branch Created Successfully".encode(ENCODING), cmd.returncode)
    store_error(repository, error)
    return error.is_error()


def merge_commit_into_current_branch(repository: str, hashcode: str) -> bool:
    cmd: Popen = Popen(["git", "merge", "--no-ff", hashcode],
                       shell=True, cwd=f"./stable_workspace/{repository}/", stdout=PIPE)
    out, err = cmd.communicate()
    if cmd.returncode != 0:
        error: Error = Error(err, cmd.returncode)
    else:
        error: Error = Error(out, cmd.returncode)
    store_error(repository, error)
    return error.is_error()


def get_branch(repository: str):
    cmd: Popen = Popen(["git", "checkout", "stable"], shell=True, cwd=f"./stable_workspace/{repository}/", stdout=PIPE)
    out, err = cmd.communicate()
    error: Error = Error(err, cmd.returncode)
    store_error(repository, error)
    return error.is_error()


def store_error(repository: str, error: Error):
    if error.is_error() or verbose:
        if repository not in error_list:
            error_list[repository] = []
        if error.is_error():
            error_list[repository].append(f"{RED}{error.get_message()}{RESET}")
        else:
            error_list[repository].append(f"{error.get_message()}")


def handle_branch(url: str, repository: str, hashcode: str):
    # By default, all methods called will return if an error has occurred and stop.
    if clone(repository, url):
        return
    if branch_exists(repository, STABLE_BRANCH_NAME):
        if checkout_branch(repository, STABLE_BRANCH_NAME):
            return
        if merge_commit_into_current_branch(repository, hashcode):
            return
    else:
        if checkout_branch(repository, hashcode):
            return
        if create_branch_from_position(repository, STABLE_BRANCH_NAME):
            return


def load_csv(file_path: str) -> []:
    with open(file_path, newline='') as csvfile:
        buildreport = csv.reader(csvfile, delimiter=",")
        repositories: [Data] = []
        for row in buildreport:
            repositories.append(Data(row[0], row[1], row[2]))

        # Remove the header
        repositories.pop(0)
        return repositories


def display_results():
    longest_key: int = 0
    longest_value: int = 0

    # pre-parse to determine size of columns
    for key, messages in error_list.items():
        if len(key) > longest_key:
            longest_key = len(key)

        for message in messages:
            cleaned: str = message.replace(RED, "").replace(RESET, "")
            if len(cleaned) > longest_value:
                longest_value = len(cleaned)

    print(f"╔═{'═' * longest_key}═╦═{'═' * longest_value}═╗")
    print(f"║ {'repo'.ljust(longest_key)} ║ {'error'.center(longest_value)} ║")
    print(f"╠═{'═' * longest_key}═╬═{'═' * longest_value}═╣")

    for repo, messages in error_list.items():
        is_first: bool = True
        for message in messages:
            message = message.replace("\n", "")
            if message != "":
                if is_first:
                    line = f"║ {repo.ljust(longest_key)} ║ {message.ljust(longest_value)} ║"
                else:
                    line = f"║ {''.ljust(longest_key)} ║ {message.ljust(longest_value)} ║"
                print(line)
            is_first = False
        print(f"╠═{'═' * longest_key}═╬═{'═' * longest_value}═╣")
    print(f"╚═{'═' * longest_key}═╩═{'═'*longest_value}═╝")


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    parser: ArgumentParser = ArgumentParser()
    parser.add_argument("--report", help="The build report to update the stable branch from.",
                        required=True,
                        type=str)
    parser.add_argument("--verbose", required=False, help="enables full logging", default=False, type=bool)
    args: Namespace = parser.parse_args()
    report: str = args.report
    verbose = args.verbose

    repositories: [Data] = load_csv(report)

    thread_pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
    for data in repositories:
        thread_pool.submit(handle_branch, url=data.get_url(), repository=data.get_repository(), hashcode=data.get_hashcode())
    thread_pool.shutdown(True)
    display_results()