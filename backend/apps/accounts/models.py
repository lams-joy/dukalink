import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from .phone import normalise_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, phone_number, password, **extra):
        if not phone_number:
            raise ValueError("A phone number is required.")
        user = self.model(phone_number=normalise_phone(phone_number), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(phone_number, password, **extra)

    def create_superuser(self, phone_number, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create(phone_number, password, **extra)

    def get_by_natural_key(self, phone_number):
        try:
            normalised = normalise_phone(phone_number)
        except ValidationError:
            raise self.model.DoesNotExist from None
        return self.get(phone_number=normalised)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=16, unique=True)  # E.164
    full_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["full_name"]

    def clean(self):
        super().clean()
        self.phone_number = normalise_phone(self.phone_number)

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"
