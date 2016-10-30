# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os
import traceback
import tarfile

from cerbero.errors import PackageNotFoundError, BuildStepError, FatalError
from cerbero.utils import _, shell
from cerbero.build.recipe import Recipe, BuildSteps
from cerbero.utils import messages as m
from cerbero.utils.shell import upload_curl, download_curl
from cerbero.packages.disttarball import DistTarball
from cerbero.packages import PackageType

class Fridge (object):
    '''
    This fridge unfreezes or freezes a cook from a recipe
    '''

    def __init__(self, store, force=False, dry_run=False):
        self.store = store
        self.cookbook = store.cookbook
        self.config = self.cookbook.get_config()
        self.force = force
        shell.DRY_RUN = dry_run
        if not os.path.exists(self.config.binaries):
            os.makedirs(self.config.binaries)

    def unfreeze_recipe(self, recipe_name, count, total):
        if not self.config.binary_repo:
           raise FatalError(_('Configuration without binary repo'))

        recipe = self.cookbook.get_recipe(recipe_name)
        steps = [BuildSteps.FETCH_BINARY, BuildSteps.EXTRACT_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def freeze_recipe(self, recipe_name, count, total):
        if not self.config.binary_repo:
           raise FatalError(_('Configuration without binary repo'))

        recipe = self.cookbook.get_recipe(recipe_name)
        steps = [BuildSteps.GEN_BINARY, BuildSteps.UPLOAD_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def fetch_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        for filename in packages_names.itervalues():
            if filename:
                download_curl(os.path.join(self.config.binary_repo, filename),
                            os.path.join(self.config.binaries, filename),
                            user=self.config.binary_repo_username,
                            password=self.config.binary_repo_password)

    def extract_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        for filename in packages_names.itervalues():
            if filename:
                tar = tarfile.open(os.path.join(self.config.binaries,
                                   filename, 'r:bz2'))
                tar.extractall(self.config.prefix)
                tar.close()

    def generate_binary(self, recipe):
        p = self.store.get_package(recipe.name)
        tar = DistTarball(self.config, p, self.store)
        p.pre_package()
        paths = tar.pack(self.config.binaries, True, self.force, False)
        p.post_package(paths)

    def upload_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        for filename in packages_names.itervalues():
            if filename:
                upload_curl(os.path.join(self.config.binaries, filename),
                            os.path.join(self.config.binary_repo, filename),
                            user=self.config.binary_repo_username,
                            password=self.config.binary_repo_password)

    def _get_packages_names(self, recipe):
        ret = {PackageType.RUNTIME: None, PackageType.DEVEL: None}
        p = self.store.get_package(recipe.name)
        tar = DistTarball(self.config, p, self.store)
        # use the package (not the packager) to avoid the warnings
        if p.files_list():
            ret[PackageType.RUNTIME] = tar.get_name(PackageType.RUNTIME)
        if p.devel_files_list():
            ret[PackageType.DEVEL] = tar.get_name(PackageType.DEVEL)
        return ret

    def _apply_steps(self, recipe, steps, count, total):
        for desc, step in steps:
            m.build_step(count, total, recipe.name, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                m.action(_("Step done"))
                continue

            # call step function
            stepfunc = getattr(self, step)
            if not stepfunc:
                raise FatalError(_('Step %s not found') % step)
            try:
                stepfunc(recipe)
                # update status successfully
                self.cookbook.update_step_status(recipe.name, step)
            except Exception:
                raise BuildStepError(recipe, step, traceback.format_exc())
