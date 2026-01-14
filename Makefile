PACKAGE=install-overwatch
VERSION=2.0
BUILD_DIR=$(CURDIR)/package
DEB_FILE=$(PACKAGE)_$(VERSION)_all.deb

.PHONY: all clean build install uninstall test

all: build

build:
	dpkg-deb --build $(BUILD_DIR)
	mv package.deb $(DEB_FILE)
	@echo "Built $(DEB_FILE)"

install: build
	sudo dpkg -i $(DEB_FILE)
	sudo systemctl daemon-reload
	sudo systemctl enable --now install_overwatch-init.service
	@echo "Installed and started install_overwatch"

uninstall:
	sudo systemctl stop install_overwatch-init.service 2>/dev/null || true
	sudo systemctl disable install_overwatch-init.service 2>/dev/null || true
	sudo dpkg -r install-overwatch
	@echo "Uninstalled install_overwatch"

test:
	@echo "Running syntax checks..."
	@find . -name "*.sh" -exec bash -n {} \;
	@python3 -m py_compile tools/workstation_snapshot.py tools/create_ansible.py tools/lib/*.py
	@echo "All syntax checks passed"

clean:
	rm -f $(DEB_FILE)
