### kc-session-manager

This is an attempt to bring some comfort to qtile life :)
This solution was testend only with: Debian 13 + lightdm + x11 + qtile.

### Introduction

When I moved to qtile it turned out that some things became unavailable.
My desktop/laptop did not go to suspend, some commands did not work.

I have been looking for something to help me like... mmm I already forgot most of them, however I recall things like: light-locker, xss, etc.

I thought if I use qtile I should try to use python to solve my issues.

### How it works

The main issue I faced with was: 
- lightdm, qtile do not work with logind (systemd-logind). It meens when you use commands like 
```shell
loginct lock-session
```
nothing happened.
When you left your pc is nothing happened with it, perhaps your screen turned off, if you use DPMS.

I found: dm-tools.
The things like lightdm/sddm have some specific (or do not have) restrictions. For example sddm does not have imbeded locker, lightdm has something like dm-tool.


