/* One stdin passphrase, two independent LUKS2 headers. No credential files.
 * cryptsetup paths and mapping names are fixed; production accepts sibling
 * block partitions only. Test builds may replace the executable and validation.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef CRYPTSETUP
#define CRYPTSETUP "/usr/sbin/cryptsetup"
#endif
static unsigned char secret[514];
static void clear_secret(void) { explicit_bzero(secret, sizeof(secret)); }
static void stop(int sig) { clear_secret(); _exit(128 + sig); }

static int sibling_partitions(const char *a, const char *b) {
#ifdef PAIR_TEST
    return strcmp(a,b) != 0;
#else
    struct stat x,y;
    char p[128],q[128],ra[PATH_MAX],rb[PATH_MAX];
    if (stat(a,&x) || stat(b,&y) || !S_ISBLK(x.st_mode) || !S_ISBLK(y.st_mode)
        || x.st_rdev == y.st_rdev) return 0;
    snprintf(p,sizeof(p),"/sys/dev/block/%u:%u/partition",major(x.st_rdev),minor(x.st_rdev));
    snprintf(q,sizeof(q),"/sys/dev/block/%u:%u/partition",major(y.st_rdev),minor(y.st_rdev));
    if (access(p,F_OK) || access(q,F_OK)) return 0;
    snprintf(p,sizeof(p),"/sys/dev/block/%u:%u/..",major(x.st_rdev),minor(x.st_rdev));
    snprintf(q,sizeof(q),"/sys/dev/block/%u:%u/..",major(y.st_rdev),minor(y.st_rdev));
    return realpath(p,ra) && realpath(q,rb) && !strcmp(ra,rb);
#endif
}

static int run(char *const args[], size_t length) {
    int pipefd[2],status=0;
    if (pipe2(pipefd,O_CLOEXEC)) return 4;
    pid_t child=fork();
    if (child < 0) { close(pipefd[0]);close(pipefd[1]);return 4; }
    if (!child) {
        clear_secret();
        sigset_t empty;
        sigemptyset(&empty);sigprocmask(SIG_SETMASK,&empty,NULL);
        if (dup2(pipefd[0],STDIN_FILENO) < 0) _exit(4);
        close(pipefd[0]);close(pipefd[1]);
        int sink=open("/dev/null",O_WRONLY);
        if (sink < 0 || dup2(sink,STDOUT_FILENO) < 0 || dup2(sink,STDERR_FILENO) < 0) _exit(4);
        if (sink > STDERR_FILENO) close(sink);
        char *env[]={"PATH=/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL=C",NULL};
        execve(CRYPTSETUP,args,env);_exit(4);
    }
    close(pipefd[0]);
    size_t done=0;
    while (done < length) {
        ssize_t amount=write(pipefd[1],secret+done,length-done);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) break;
        done+=(size_t)amount;
    }
    close(pipefd[1]);
    while (waitpid(child,&status,0) < 0) { if (errno != EINTR) return 4; }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 4;
}

static int close_mapping(const char *name) {
    char *args[]={CRYPTSETUP,"close",(char *)name,NULL};
    return run(args,0);
}

int main(int argc,char **argv) {
    struct rlimit core={0,0};
    if (setrlimit(RLIMIT_CORE,&core) || prctl(PR_SET_DUMPABLE,0,0,0,0)) return 4;
    if (argc != 4 || strcmp(argv[1],"--stdin") || !sibling_partitions(argv[2],argv[3])) return 4;
    if (access("/dev/mapper/portable_os",F_OK)==0 || access("/dev/mapper/portable_system",F_OK)==0) return 4;
    if (mlock(secret,sizeof(secret))) return 4;
    atexit(clear_secret);
    signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGHUP,stop);signal(SIGPIPE,SIG_IGN);
    size_t used=0;
    while (used < sizeof(secret)) {
        ssize_t amount=read(STDIN_FILENO,secret+used,sizeof(secret)-used);
        if (amount < 0 && errno == EINTR) continue;
        if (amount < 0) return 4;
        if (!amount) break;
        used+=(size_t)amount;
    }
    if (used && secret[used-1]=='\n') --used;
    if (!used || used > 512 || memchr(secret,0,used) || memchr(secret,'\n',used) || memchr(secret,'\r',used)) return 4;
    /* SIGTERM/INT cannot leave half of a pair open once OS activation starts.
     * They are deferred through the bounded pair transaction; cryptsetup errors
     * close the OS mapping. A killed process still has no persistent passphrase.
     */
    sigset_t blocked,old;
    sigemptyset(&blocked);sigaddset(&blocked,SIGINT);sigaddset(&blocked,SIGTERM);sigaddset(&blocked,SIGHUP);
    sigprocmask(SIG_BLOCK,&blocked,&old);
    char *osargs[]={CRYPTSETUP,"open","--type","luks2","--readonly","--tries","1","--key-file","-",argv[2],"portable_os",NULL};
    int result=run(osargs,used);
    if (result) return result==2 ? 2 : 4;
    char *systemargs[]={CRYPTSETUP,"open","--type","luks2","--tries","1","--key-file","-",argv[3],"portable_system",NULL};
    result=run(systemargs,used);
    clear_secret();
    if (result) {
        int closed=close_mapping("portable_os");
        /* 3 distinguishes a mismatched settings passphrase from an OS retry. */
        result=closed ? 4 : 3;
    }
    sigset_t pending;
    sigpending(&pending);
    if (!result && (sigismember(&pending,SIGINT) || sigismember(&pending,SIGTERM) || sigismember(&pending,SIGHUP))) {
        int closed_system=close_mapping("portable_system");
        int closed_os=close_mapping("portable_os");
        (void)closed_system;(void)closed_os;
        return 4;
    }
    sigprocmask(SIG_SETMASK,&old,NULL);
    return result;
}
