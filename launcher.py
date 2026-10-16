"""EXE(PyInstaller) 진입점."""

import sys

if __name__ == "__main__":
    from mc_server_maker.core import updater

    # started by the previous version to install this one over it: copy, restart, done
    if not updater.run_installer(sys.argv):
        from mc_server_maker.gui.app import main

        main()
