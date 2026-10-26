/*
 * cf-launch: privilege-dropping exec helper used by the sandbox runner.
 *
 *   cf-launch <acct_fd> <uid> <gid> <cpu_seconds> <address_space_bytes> <stack_bytes> -- argv...
 *
 * Why a separate C program? Linux carries a process's peak-RSS high-water mark
 * across fork+exec, so a program forked directly from the (Python) runner would
 * report the runner's ~12 MB as its own minimum memory usage. Forking from this
 * tiny static binary instead makes ru_maxrss reflect the submitted program.
 *
 * The launcher forks; the child drops all groups, switches to uid/gid, applies
 * rlimits and execs argv (never through a shell). The parent waits with wait4()
 * and writes one line of accounting to acct_fd:
 *
 *   <exit_code|-1> <signal|0> <user_us> <sys_us> <maxrss_kb>
 *
 * stdin/stdout/stderr are inherited unchanged by the program.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

static void set_limit(int resource, rlim_t soft, rlim_t hard) {
    struct rlimit rl = {soft, hard};
    if (setrlimit(resource, &rl) != 0) _exit(126);
}

int main(int argc, char **argv) {
    if (argc < 9 || strcmp(argv[7], "--") != 0) {
        fprintf(stderr, "usage: cf-launch acct_fd uid gid cpu_s as_bytes stack_bytes -- argv...\n");
        return 125;
    }
    int acct_fd = atoi(argv[1]);
    uid_t uid = (uid_t)strtoul(argv[2], NULL, 10);
    gid_t gid = (gid_t)strtoul(argv[3], NULL, 10);
    long cpu = strtol(argv[4], NULL, 10);
    unsigned long long as = strtoull(argv[5], NULL, 10);
    unsigned long long stack = strtoull(argv[6], NULL, 10);
    char **cmd = &argv[8];

    pid_t pid = fork();
    if (pid < 0) return 124;
    if (pid == 0) {
        close(acct_fd); /* accounting channel stays with the trusted parent */
        if (setgroups(0, NULL) != 0) _exit(126);
        if (setresgid(gid, gid, gid) != 0) _exit(126);
        if (setresuid(uid, uid, uid) != 0) _exit(126);
        set_limit(RLIMIT_CORE, 0, 0);
        set_limit(RLIMIT_NOFILE, 64, 64);
        set_limit(RLIMIT_FSIZE, 16ULL << 20, 16ULL << 20);
        if (cpu > 0) set_limit(RLIMIT_CPU, (rlim_t)cpu, (rlim_t)cpu + 1);
        if (stack > 0) set_limit(RLIMIT_STACK, (rlim_t)stack, (rlim_t)stack);
        if (as > 0) set_limit(RLIMIT_AS, (rlim_t)as, (rlim_t)as);
        execv(cmd[0], cmd);
        _exit(127);
    }

    int status = 0;
    struct rusage ru;
    while (wait4(pid, &status, 0, &ru) < 0) {
        if (errno != EINTR) return 123;
    }
    FILE *acct = fdopen(acct_fd, "w");
    if (acct) {
        fprintf(acct, "%d %d %lld %lld %ld\n",
                WIFEXITED(status) ? WEXITSTATUS(status) : -1,
                WIFSIGNALED(status) ? WTERMSIG(status) : 0,
                (long long)ru.ru_utime.tv_sec * 1000000LL + ru.ru_utime.tv_usec,
                (long long)ru.ru_stime.tv_sec * 1000000LL + ru.ru_stime.tv_usec,
                ru.ru_maxrss);
        fclose(acct);
    }
    return 0;
}
