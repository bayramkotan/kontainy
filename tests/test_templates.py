"""Templates exist so nobody has to hunt for example code. They must be right."""

import pytest

from kontainy.core import templates


def test_ids_are_unique():
    ids = [t.id for t in templates.TEMPLATES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("template", templates.TEMPLATES,
                         ids=lambda t: t.id)
def test_template_renders_three_ways(template):
    run = template.run_command("podman")
    assert run.startswith("podman run")
    assert template.image.split(":")[0] in run
    quadlet = template.quadlet()
    assert "[Container]" in quadlet and "[Install]" in quadlet
    assert f"Image={template.image}" in quadlet
    compose = template.compose()
    assert "services:" in compose and template.image in compose


@pytest.mark.parametrize("template", templates.TEMPLATES, ids=lambda t: t.id)
def test_images_are_fully_qualified(template):
    """Podman does not assume docker.io; short names break under
    short-name-mode=enforcing, which is the default on Arch."""
    assert "/" in template.image, f"{template.id}: image needs a registry"


@pytest.mark.parametrize("template", templates.TEMPLATES, ids=lambda t: t.id)
def test_no_template_is_privileged(template):
    run = template.run_command()
    assert "--privileged" not in run


def test_categories_match():
    for template in templates.TEMPLATES:
        assert template.category in templates.CATEGORIES
