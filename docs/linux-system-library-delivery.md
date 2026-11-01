# Linux system-library supplier evidence

The Linux executable bundles its selected native shared-library dependencies.
End users do not need Python, Node, compilers or development packages. Libraries
originating in Ubuntu are reviewed independently from Python wheels, Qt sources,
audio tools and the managed game readers.

`scripts/build-linux-system-resources.py` runs on the Ubuntu Noble x64 build
runner before native compilation and freezing. Its source-controlled policy is
`packaging/desktop/linux-system-inputs.json`. The policy pins the official Ubuntu
archive keyring bytes and the Archive Automatic Signing Key (2018). It permits
only the named source packages and the Noble, Noble Updates and Noble Security
main/universe indexes. A host package database or self-declared receipt cannot
authorize a binary.

The collection retains and verifies this chain:

1. The exact archive keyring and signed `InRelease` files, verified with an
   isolated GnuPG home and the explicitly allowed signing-key fingerprint.
2. Full binary `Packages` and source `Sources` indexes. Their compressed bytes
   must match the signed SHA256 entries. Acquisition uses by-hash URLs to avoid
   racing an index update.
3. Each selected original `.deb`, bound to the signed package name, version,
   architecture, size and SHA256. The installed library must be byte-identical
   to a regular member of that archive.
4. Every archive in the matching signed source-version record: original source,
   Debian packaging and patches, and the `.dsc` source recipe. Explicit binary
   `Source: name (version)` fields are honored; a binary rebuild version never
   substitutes for a different source version.
5. Complete package copyright and license notices, plus the full common license
   terms from the independently authenticated `base-files` package. The notice
   index identifies the exact supplier archive member for each retained text.

Debian source format 1.0 carries packaging files in a `.diff.gz`. Its copyright
reader accepts only a complete new-file hunk with exact line counts; it never
executes a patch or accepts a partial notice. Detached archive signatures remain
authenticated source-record files and are not interpreted as tar streams.
For libxcb, the policy records the upstream packaging rule that concatenates
`debian/copyright.debian` and `COPYING`. Review retains both inputs, checks the
exact rule, reproduces only that concatenation and requires byte equality with
the copyright shipped in the authenticated binary package.

The resource manifest binds the collector, verifier and policy to the candidate
source. The independent final-payload reviewer rechecks archive signatures,
indexes, binary members, corresponding source and notice bytes. Only then can an
actual final ELF hash gain a supplier origin. An unknown native dependency still
fails the final inventory review, even if the rest of the collection is valid.

Default collection is read-only with respect to the operating system. The
explicit `--sync-build-host` mode is restricted to the CI invocation. It upgrades
only the selected installed package owners to explicit versions from the already
authenticated indexes before their bytes are collected or used in construction.
This accommodates hosted runners whose preinstalled package versions have been
superseded. It never installs packages in a user's application or runs on this
project's Windows development host. Unavailable source versions remain failures.

The supplied libraries remain dynamically replaceable. The application does not
restrict reverse engineering needed to debug modifications of LGPL libraries.
Original source archives preserve upstream terms and the distribution's build
instructions. Exact supplier correspondence is not an independent reproduction
of Ubuntu's compiled output, a legal certification, or a native execution test.

Validation on 2026-11-01: authored regressions cover signature authorization,
signed-index hashes, Debian Zstandard/XZ streams, archive traversal, exact source
versions, binary identities, full notices, attribution and missing source bytes.
A read-only official-archive probe verified the full chain for `libexpat1`
2.6.1-2ubuntu0.6 and `base-files` 13ubuntu10.5, including 18 full notices and seven
source/binary archives. Its Expat ELF matches the previously observed Linux
candidate. The complete installed-library set requires the hosted Linux
collection and final input review; those results are not inferred from the
representative probe.

A further read-only audit checked the authenticated owners of all 89 selected
library names and their 95 available source versions across the three pockets.
All 95 source copyright checks passed, including libxcb's exact generated
copyright comparison against its binary package. This tests supplier formats and
policy coverage; the runner's actual installed bytes and final payload still
require the hosted collection and independent inventory review.

References: [Ubuntu archive integrity](https://documentation.ubuntu.com/security/docs/software-integrity/archive-verification/),
[official archive keyring](https://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg),
[Debian repository format](https://wiki.debian.org/DebianRepository/Format), and
[Ubuntu archive snapshots](https://snapshot.ubuntu.com/).
