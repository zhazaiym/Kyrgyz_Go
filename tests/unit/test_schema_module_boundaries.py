def test_schema_compatibility_module_reexports_domain_types():
    from mysite.database import schema as legacy_schema
    from mysite.database.catalogue_schema import HelicopterTourOutSchema, TrekkingOutSchema
    from mysite.database.schema import AdminLoginSchema, ContactInputSchema
    from mysite.database.schema import HelicopterTourOutSchema as LegacyHelicopterTourOutSchema
    from mysite.database.schema import TourInputSchema, TravelRequestOutSchema
    from mysite.database.schemas.admin import AdminLoginSchema as DomainAdminLoginSchema
    from mysite.database.schemas.catalogue import (
        HelicopterTourOutSchema as CatalogueHelicopterTourOutSchema)
    from mysite.database.schemas.catalogue import TourInputSchema as CatalogueTourInputSchema
    from mysite.database.schemas.catalogue import TrekkingOutSchema as CatalogueTrekkingOutSchema
    from mysite.database.schemas.content import ContactInputSchema as ContentContactInputSchema
    from mysite.database.schemas.requests import TravelRequestOutSchema as RequestOutSchema

    assert TourInputSchema is CatalogueTourInputSchema
    assert AdminLoginSchema is DomainAdminLoginSchema
    assert ContactInputSchema is ContentContactInputSchema
    assert TravelRequestOutSchema is RequestOutSchema
    assert LegacyHelicopterTourOutSchema is CatalogueHelicopterTourOutSchema
    assert HelicopterTourOutSchema is CatalogueHelicopterTourOutSchema
    assert TrekkingOutSchema is CatalogueTrekkingOutSchema
    assert len(legacy_schema.__all__) == 67
    assert all(isinstance(getattr(legacy_schema, name), type) for name in legacy_schema.__all__)
