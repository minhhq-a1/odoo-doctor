import json
import paramiko
import requests
import yaml

try:
    import boto3
except ImportError:
    boto3 = None

from odoo import models


class Client(models.AbstractModel):
    _name = "deps.client"
    _description = "Client"
