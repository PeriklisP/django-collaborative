import logging

from dateutil import parser as dt_parser
from import_export.resources import (
    # modelresource_factory,
    ModelResource, ModelDeclarativeMetaclass,
)
from tablib import Dataset

from django_models_from_csv import models
from django_models_from_csv.utils.csv import fetch_csv


logger = logging.getLogger(__name__)


def modelresource_factory(model, resource_class=ModelResource, extra_attrs=None):
    """
    Factory for creating ``ModelResource`` class for given Django model.
    """
    attrs = {'model': model}
    if extra_attrs:
        attrs.update(extra_attrs)

    Meta = type(str('Meta'), (object,), attrs)

    class_name = model.__name__ + 'Resource'

    class_attrs = {
        'Meta': Meta,
    }

    metaclass = ModelDeclarativeMetaclass
    return metaclass(class_name, (resource_class,), class_attrs)


def import_records_list(csv, dynmodel):
    """
    Take a fetched CSV and turn it into a tablib Dataset, with
    a row ID column and all headers translated to model field names.
    """
    data = Dataset().load(csv)
    # add an ID column matching the row number
    if dynmodel.csv_url:
        data.insert_col(0, col=[i+1 for i in range(len(data))], header='id')
    # # screendoor: use the builtin ID field
    # elif dynmodel.csv_url:
    #     # data.insert_col(0, col=[i+1 for i in range(len(data))], header='id')

    # Turn our CSV columns into model columns
    for i in range(len(data.headers)):
        header = data.headers[i]
        model_header = dynmodel.csv_header_to_model_header(header)
        if model_header and header != model_header:
            data.headers[i] = model_header

    datetime_ixs = []
    date_ixs = []
    for c in dynmodel.columns:
        c_type = c.get("type")
        type_ixs = None
        if c_type and c_type == "datetime":
            type_ixs = datetime_ixs
        elif c_type and c_type == "date":
            type_ixs = date_ixs
        else:
            continue

        name = c["name"]
        try:
            ix = data.headers.index(name)
        except ValueError:
            # Possibly a new column not in dynamic model description, ignore
            continue
        type_ixs.append(ix)

    newdata = Dataset(headers=data.headers)
    for row in data:
        newrow = []
        for i in range(len(row)):
            val = row[i]
            if i in datetime_ixs:
                if not val:
                    newrow.append(None)
                    continue
                try:
                    val = dt_parser.parse(val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.error("Error parsing datetime: %s" % e)
                    newrow.append(None)
                    continue
            elif i in date_ixs:
                if not val:
                    newrow.append(None)
                    continue
                try:
                    val = dt_parser.parse(val).strftime("%Y-%m-%d")
                except Exception as e:
                    logger.error("Error parsing date: %s" % e)
                    newrow.append(None)
                    continue
            newrow.append(val)
        newdata.append(newrow)
    return newdata


def import_records(csv, Model, dynmodel):
    """
    Take a fetched CSV, parse it into user rows for
    insertion and attempt to import the data into the
    specified model.

    This performs a pre-import routine which will return
    failure information we can display and let the user fix
    the dynmodel before trying again. On success this function
    returns None.

    TODO: Only show N number of errors. If there are more,
    tell the user more errors have been supressed and to
    fix the ones listed before continuing. We don't want
    to overwhelm the user with error messages.
    """
    resource = modelresource_factory(model=Model)()
    dataset = import_records_list(csv, dynmodel)
    logger.debug("Importing CSV:\n%s" % dataset.export("csv"))
    result = resource.import_data(dataset, dry_run=True)
    logger.debug("DRY RUN: Result has errors? %s" % result.has_errors())
    # TODO: transform errors to something readable
    if result.has_errors():
        errors = result.row_errors()
        logger.debug("DRY RUN: Errors: %s" % errors)
        return errors
    # TODO: Better error handling. There are some strange situations
    # where the importer will silently fail, despite has_errors, above,
    # returning False. This will prevent bad imports and actually show
    # an error, no matter how ugly. One such situation is attempting to
    # import a badly formatted date into a DateField.
    try:
        result = resource.import_data(
            dataset, dry_run=False, raise_errors=True
        )
    except Exception as e:
        return e
    if result.has_errors():
        errors = result.row_errors()
        return errors


def update_records(csv, Model, dynmodel):
    """
    Take a CSV and update an existing model. Here, we want
    to reconcile old records with the new ones. We do this in
    the following ways:

    Screendoor:

        1. Use their ID. Done!

    Google sheets:

        1. Make sure we have a timestamp field.
        2. Go through the rows, looking up each corresponding ID.
        3. Check the timestamp to ensure we've got the same record.
        4. a. If it's different, scan the list to see if we have
              a following matching record.
    """
    pass
