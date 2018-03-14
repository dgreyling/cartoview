from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import json
import logging
from builtins import *
from sys import stdout

from django.conf import settings as geonode_settings
from django.contrib.gis.db import models
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.db.models import signals
from future import standard_library
from jsonfield import JSONField
from taggit.managers import TaggableManager
# Create your models here.
from geonode.base.models import ResourceBase, resourcebase_post_save
from geonode.maps.models import Map as GeonodeMap
from geonode.security.models import remove_object_permissions
from taggit.managers import TaggableManager
from jsonfield import JSONField
from django.contrib.auth.models import Group
from geonode.security.models import set_owner_permissions
from guardian.shortcuts import assign_perm
from django.contrib.auth import get_user_model


from .config import AppsConfig

standard_library.install_aliases()

formatter = logging.Formatter(
    '[%(asctime)s] p%(process)s  { %(name)s %(pathname)s:%(lineno)d} \
                            %(levelname)s - %(message)s', '%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


class AppTypeManager(models.Manager):
    def without_apps_duplication(self):
        return super(AppTypeManager, self).get_queryset().distinct('apps')


class AppType(models.Model):
    name = models.CharField(max_length=200, unique=True)
    objects = AppTypeManager()

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name


class AppStore(models.Model):
    """
    to store links for cartoview appstores
    """
    name = models.CharField(max_length=256)
    url = models.URLField(verbose_name="App Store URL")
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def __unicode__(self):
        return self.name


class App(models.Model):
    def only_filename(instance, filename):
        return filename

    name = models.CharField(max_length=200, null=True, blank=True)
    title = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    short_description = models.TextField(null=True, blank=True)
    app_url = models.URLField(null=True, blank=True)
    author = models.CharField(max_length=200, null=True, blank=True)
    author_website = models.URLField(null=True, blank=True)
    license = models.CharField(max_length=200, null=True, blank=True)
    tags = TaggableManager()
    date_installed = models.DateTimeField(
        'Date Installed', auto_now_add=True, null=True)
    installed_by = models.ForeignKey(
        geonode_settings.AUTH_USER_MODEL, null=True, blank=True)
    single_instance = models.BooleanField(
        default=False, null=False, blank=False)
    category = models.ManyToManyField(
        AppType, related_name='apps')
    license = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(
        max_length=100, blank=False, null=False, default='Alpha')
    owner_url = models.URLField(null=True, blank=True)
    help_url = models.URLField(null=True, blank=True)
    app_img_url = models.TextField(max_length=1000, blank=True, null=True)
    rating = models.IntegerField(default=0, null=True, blank=True)
    contact_name = models.CharField(max_length=200, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    version = models.CharField(max_length=10)
    store = models.ForeignKey(AppStore, null=True)
    order = models.IntegerField(null=True, default=0)
    default_config = JSONField(default={})

    class meta(object):
        ordering = ['order']

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title

    @property
    def settings_url(self):
        try:
            return reverse("%s_settings" % self.name)
        except BaseException as e:
            logger.error(e.message)
            return None

    @property
    def new_url(self):
        try:
            return reverse("%s.new" % self.name)
        except BaseException as e:
            logger.error(e.message)
            return None

    _apps_config = None

    @property
    def apps_config(self):
        if App._apps_config is None:
            App._apps_config = AppsConfig()
        return App._apps_config

    @property
    def config(self):
        return self.apps_config.get_by_name(self.name)


class AppInstance(ResourceBase):
    """
    An App Instance  is any kind of App Instance that can be created
    out of one of the Installed Apps.
    """

    # Relation to the App model
    app = models.ForeignKey(App, null=True, blank=True)
    config = models.TextField(null=True, blank=True)
    map = models.ForeignKey(GeonodeMap, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('appinstance_detail', args=(self.id,))

    def set_permissions(self, perm_spec):
        '''
        FIXME:the following Model is a temp solution to skip setting geofence
        rules for app instances please take a look https://github.com/GeoNode/geonode/blob/80229ad5f2aae7ef2de4d6c9a352af8a3fbde702/geonode/security/models.py#L224
        '''

        remove_object_permissions(self)

        # default permissions for resource owner
        set_owner_permissions(self)

        if 'users' in perm_spec and "AnonymousUser" in perm_spec['users']:
            anonymous_group = Group.objects.get(name='anonymous')
            for perm in perm_spec['users']['AnonymousUser']:
                if self.polymorphic_ctype.name == 'layer' and\
                    perm in ('change_layer_data', 'change_layer_style',
                             'add_layer', 'change_layer', 'delete_layer',):
                    assign_perm(perm, anonymous_group, self.layer)
                else:
                    assign_perm(perm, anonymous_group,
                                self.get_self_resource())

        if 'users' in perm_spec:
            for user, perms in perm_spec['users'].items():
                user = get_user_model().objects.get(username=user)
                geofence_user = str(user)
                if "AnonymousUser" in geofence_user:
                    geofence_user = None
                for perm in perms:
                    if self.polymorphic_ctype.name == 'layer' and perm in (
                            'change_layer_data', 'change_layer_style',
                            'add_layer', 'change_layer', 'delete_layer',):
                        assign_perm(perm, user, self.layer)
                    else:
                        assign_perm(perm, user, self.get_self_resource())

        if 'groups' in perm_spec:
            for group, perms in perm_spec['groups'].items():
                group = Group.objects.get(name=group)
                for perm in perms:
                    if self.polymorphic_ctype.name == 'layer' and perm in (
                            'change_layer_data', 'change_layer_style',
                            'add_layer', 'change_layer', 'delete_layer',):
                        assign_perm(perm, group, self.layer)
                    else:
                        assign_perm(perm, group, self.get_self_resource())

    @property
    def name_long(self):
        if not self.title:
            return str(self.id)
        else:
            return '%s (%s)' % (self.title, self.id)

    @property
    def config_obj(self):
        try:
            return json.loads(self.config)
        except BaseException as e:
            logger.error(e.message)
            return None

    @property
    def launch_url(self):
        return reverse("%s.view" % self.app.name, args=[self.pk])

    def get_thumbnail_url(self):
        return self.thumbnail_url


def pre_save_appinstance(instance, sender, **kwargs):
    if not isinstance(instance, AppInstance):
        return
    if instance.abstract == '' or instance.abstract is None:
        instance.abstract = 'No abstract provided'

    if instance.title == '' or instance.title is None:
        instance.title = 'No title provided'


def pre_delete_appinstance(instance, sender, **kwargs):
    if not isinstance(instance, AppInstance):
        return
    remove_object_permissions(instance.get_self_resource())


def appinstance_post_save(instance, *args, **kwargs):
    if not isinstance(instance, AppInstance):
        return
    resourcebase_post_save(instance, args, kwargs)


signals.pre_save.connect(pre_save_appinstance)
signals.post_save.connect(appinstance_post_save)
signals.pre_delete.connect(pre_delete_appinstance)
