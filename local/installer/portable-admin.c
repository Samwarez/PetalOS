/* Portable PetalOS administrator bootstrap. No setuid installation is used.
 * pkexec authorizes this static executable. It accepts only the build-pinned
 * file stream on stdin, never paths, commands, credentials or environment
 * overrides. Only the verified, root-owned copy is executed as the worker.
 */
#define _GNU_SOURCE
#define _XOPEN_SOURCE 700
#include <errno.h>
#include <fcntl.h>
#include <ftw.h>
#include <limits.h>
#include <linux/if_alg.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include "portable-pin.h"

static char stage[PATH_MAX];
static char caller_uid[32] = "0";
static uint64_t consumed;
static int hashfd = -1;
static volatile sig_atomic_t stopped;
static volatile sig_atomic_t child;
static int supervisor = 1;

static int remove_entry(const char *path, const struct stat *info, int type, struct FTW *walk) {
    (void)info; (void)type; (void)walk;
    return remove(path);
}
static void cleanup(void) {
    if (supervisor && stage[0]) {
        if (nftw(stage, remove_entry, 32, FTW_DEPTH | FTW_PHYS) != 0)
            fputs("{\"type\":\"error\",\"message\":\"Temporary backend cleanup is incomplete; its root-only directory remains under /run.\"}\n", stdout);
        stage[0] = 0;
    }
}
static void die(const char *message) {
    /* All callers use fixed, credential-free messages. */
    printf("{\"type\":\"error\",\"message\":\"%s\"}\n", message);
    fflush(stdout); exit(1);
}
static void interrupted(int sig) {
    stopped = sig;
    if (child > 0) kill((pid_t)child, SIGTERM);
}
static void exact(void *destination, size_t size) {
    unsigned char *out = destination;
    if (size > PAYLOAD_BYTES - consumed) die("Portable backend stream exceeded its build limit.");
    while (size) {
        if (stopped) die("Portable backend preparation was cancelled.");
        struct pollfd input = {.fd = STDIN_FILENO, .events = POLLIN};
        int ready = poll(&input, 1, 120000);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0) die("Portable backend input timed out.");
        ssize_t count = read(STDIN_FILENO, out, size);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) die("Portable backend input ended before verification.");
        ssize_t hashed = send(hashfd, out, (size_t)count, MSG_MORE | MSG_NOSIGNAL);
        if (hashed != count) die("The Linux SHA-256 service could not verify the portable backend.");
        consumed += (uint64_t)count; out += count; size -= (size_t)count;
    }
}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t le64(const unsigned char *p) {
    return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32;
}
static void valid_path(const char *name, size_t size) {
    if (strlen(name) != size || (strncmp(name, "app/", 4) && strncmp(name, "runtime/", 8)))
        die("Portable backend contains an invalid path.");
    const char *part = name;
    for (const char *p = name;; ++p) {
        if (*p != '/' && *p) continue;
        size_t n = (size_t)(p - part);
        if (!n || (n == 1 && part[0] == '.') || (n == 2 && part[0] == '.' && part[1] == '.'))
            die("Portable backend contains a redirected path.");
        if (!*p) break;
        part = p + 1;
    }
}
static void parents(char *path) {
    for (char *p = path + strlen(stage) + 1; *p; ++p) {
        if (*p != '/') continue;
        *p = 0;
        if (mkdir(path, 0755) != 0 && errno != EEXIST) die("Could not prepare the temporary backend directory.");
        struct stat info;
        if (lstat(path, &info) != 0 || !S_ISDIR(info.st_mode) || info.st_uid != 0 || (info.st_mode & 0022))
            die("Temporary backend directory protection failed.");
        *p = '/';
    }
}
static void extract(void) {
    unsigned char header[16], buffer[65536];
    unsigned entries = 0;
    for (;;) {
        exact(header, sizeof(header));
        uint32_t length = le32(header), mode = le32(header + 4);
        uint64_t size = le64(header + 8);
        if (!length) {
            if (mode || size || consumed != PAYLOAD_BYTES) die("Portable backend stream has an invalid end marker.");
            break;
        }
        if (++entries > 100000 || length >= PATH_MAX || (mode != 0644 && mode != 0755) || size > PAYLOAD_BYTES)
            die("Portable backend entry exceeded its build limits.");
        char name[PATH_MAX], destination[PATH_MAX];
        exact(name, length); name[length] = 0; valid_path(name, length);
        if (snprintf(destination, sizeof(destination), "%s/%s", stage, name) >= (int)sizeof(destination))
            die("Portable backend path is too long.");
        parents(destination);
        int fd = open(destination, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (fd < 0) die("Portable backend contains a duplicate or unavailable file.");
        while (size) {
            size_t count = size < sizeof(buffer) ? (size_t)size : sizeof(buffer);
            exact(buffer, count);
            size_t offset = 0;
            while (offset < count) {
                ssize_t written = write(fd, buffer + offset, count - offset);
                if (written < 0 && errno == EINTR) continue;
                if (written <= 0) die("Temporary backend storage is full or unavailable.");
                offset += (size_t)written;
            }
            size -= count;
        }
        if (fchmod(fd, (mode_t)mode) || close(fd)) die("Could not protect the temporary backend file.");
    }
    if (send(hashfd, "", 0, MSG_NOSIGNAL) < 0) die("Could not finish portable backend verification.");
    unsigned char digest[32]; char hex[65];
    if (read(hashfd, digest, sizeof(digest)) != (ssize_t)sizeof(digest)) die("Could not read portable backend verification.");
    for (unsigned i = 0; i < sizeof(digest); ++i) snprintf(hex + i * 2, 3, "%02x", digest[i]);
    if (strcmp(hex, PAYLOAD_SHA256)) die("Portable backend differs from this application build; nothing was executed.");
    close(hashfd); hashfd = -1;
}
static void worker(void) {
    if (prctl(PR_SET_PDEATHSIG, SIGTERM) || getppid() == 1) _exit(1);
    if (unshare(CLONE_NEWNS) || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL))
        die("This Linux system does not allow the temporary backend mount namespace.");
    char source[PATH_MAX], backend[PATH_MAX];
    snprintf(source, sizeof(source), "%s/runtime/usr", stage);
    if (mount(source, "/usr", NULL, MS_BIND | MS_REC, NULL) ||
        mount(NULL, "/usr", NULL, MS_BIND | MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL))
        die("Could not activate the verified portable runtime.");
    snprintf(backend, sizeof(backend), "%s/app/backend.py", stage);
    clearenv();
    char supervisor_pid[32];
    snprintf(supervisor_pid, sizeof(supervisor_pid), "%ld", (long)getppid());
    setenv("PETALOS_SUPERVISOR_PID", supervisor_pid, 1);
    setenv("BLOOM_CALLER_UID", caller_uid, 1);
    setenv("PATH", "/usr/sbin:/usr/bin:/sbin:/bin", 1);
    setenv("HOME", stage, 1); setenv("LC_ALL", "C.UTF-8", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    if (chdir("/")) die("Could not start the temporary backend.");
    puts("{\"type\":\"portable-ready\"}");
    execl("/usr/bin/python3", "python3", "-I", "-B", backend, (char *)NULL);
    die("Could not start the verified administrator worker.");
}
int main(int argc, char **argv) {
    (void)argv;
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (argc != 1 || geteuid() != 0 || getuid() != 0) die("The portable backend requires administrator authorization and no arguments.");
    const char *pk_uid = getenv("PKEXEC_UID");
    if (pk_uid) {
        size_t n = strlen(pk_uid);
        if (!n || n >= sizeof(caller_uid) || strspn(pk_uid, "0123456789") != n)
            die("Could not identify the authorizing desktop user.");
        memcpy(caller_uid, pk_uid, n + 1);
    }
    struct rlimit core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &core) || prctl(PR_SET_DUMPABLE, 0)) die("Could not protect the temporary backend process.");
    umask(0077);
    for (int sig = 1; sig < NSIG; ++sig) {
        if (sig == SIGINT || sig == SIGTERM || sig == SIGHUP) {
            struct sigaction action = {.sa_handler = interrupted};
            sigemptyset(&action.sa_mask); sigaction(sig, &action, NULL);
        }
    }
    struct stat info;
    if (lstat("/run", &info) || !S_ISDIR(info.st_mode) || info.st_uid != 0 || (info.st_mode & 0022))
        die("A protected /run directory is required for portable administrator operations.");
    if (strcmp(realpath("/bin", (char[PATH_MAX]){0}) ?: "", "/usr/bin") ||
        strcmp(realpath("/lib", (char[PATH_MAX]){0}) ?: "", "/usr/lib") ||
        strcmp(realpath("/lib64", (char[PATH_MAX]){0}) ?: "", "/usr/lib64"))
        die("Portable drive operations currently require an amd64 Linux system with merged /usr directories.");
    int algorithm = socket(AF_ALG, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_alg address = {.salg_family = AF_ALG, .salg_type = "hash", .salg_name = "sha256"};
    if (algorithm < 0 || bind(algorithm, (struct sockaddr *)&address, sizeof(address)) ||
        (hashfd = accept4(algorithm, NULL, NULL, SOCK_CLOEXEC)) < 0)
        die("This Linux kernel needs its SHA-256 hash API for portable administrator operations.");
    close(algorithm);
    strcpy(stage, "/run/petalos-installer-XXXXXX");
    if (!mkdtemp(stage)) {stage[0] = 0; die("Could not create the temporary administrator backend.");}
    atexit(cleanup);
    puts("{\"type\":\"progress\",\"value\":{\"stage\":\"preparing-portable-backend\"}}");
    extract();
    if (stopped) die("Portable backend preparation was cancelled.");
    pid_t process = fork();
    if (process < 0) die("Could not launch the temporary administrator worker.");
    if (!process) { /* Cleanup belongs to the supervisor, after the namespace exits. */
        supervisor = 0;
        worker(); _exit(1);
    }
    child = (sig_atomic_t)process;
    if (stopped) kill(process, SIGTERM);
    int status;
    while (waitpid(process, &status, 0) < 0) if (errno != EINTR) die("Could not wait for administrator cleanup.");
    child = 0;
    cleanup();
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
