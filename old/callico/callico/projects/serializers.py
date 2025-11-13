from rest_framework import serializers

from callico.projects.models import AuthorityValue, Element, Project, Provider


class ProviderSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="get_type_display")

    class Meta:
        model = Provider
        fields = ["name", "type"]


class ProjectSerializer(serializers.ModelSerializer):
    provider = ProviderSerializer()

    class Meta:
        model = Project
        fields = ("id", "name", "public", "provider", "provider_object_id")


class ElementLightSerializer(serializers.ModelSerializer):
    image = serializers.DictField(source="serialize_image")

    class Meta:
        model = Element
        fields = ("id", "name", "polygon", "image")


class ElementSerializer(ElementLightSerializer):
    children = ElementLightSerializer(many=True)

    class Meta:
        model = Element
        fields = ElementLightSerializer.Meta.fields + ("parent_id", "children")


class AuthorityValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthorityValue
        fields = ("value",)
