"""
Core library for working with `Concept Maps <https://www.hl7.org/fhir/conceptmap.html>`_
and `Value Sets <https://www.hl7.org/fhir/valueset.html>`_, and hierarchical code systems
in Bunsen. See the :py:class:`~bunsen.mapping.ConceptMaps` class,
:py:class `~bunsen.mapping.ValueSets` class, and :py:class `~bunsen.mapping.Hierarchies`
class for details.
"""

from pyspark.sql import functions, DataFrame
import collections
import datetime

def get_concept_maps(spark_session, database='ontologies'):
    """
    Returns a :class:`ConceptMaps` instance for the given database.
    """
    jconcept_maps = spark_session._jvm.com.cerner.bunsen.mappings \
      .ConceptMaps.getFromDatabase(spark_session._jsparkSession, database)

    return ConceptMaps(spark_session, jconcept_maps)

def create_concept_maps(spark_session):
    """
    Creates a new, empty :py:class:`ConceptMaps` instance.
    """
    jconcept_maps = spark_session._jvm.com.cerner.bunsen.mappings \
      .ConceptMaps.getEmpty(spark_session._jsparkSession)

    return ConceptMaps(spark_session, jconcept_maps)

def get_value_sets(spark_session, database='ontologies'):
    """
    Returns a :class:`ValueSets` instance for the given database.
    """
    jvalue_sets = spark_session._jvm.com.cerner.bunsen.mappings \
      .ValueSets.getFromDatabase(spark_session._jsparkSession, database)

    return ValueSets(spark_session, jvalue_sets)

def create_value_sets(spark_session):
    """
    Creates a new, empty :class:`ValueSets` instance.
    """
    jvalue_sets = spark_session._jvm.com.cerner.bunsen.mappings \
      .ValueSets.getEmpty(spark_session._jsparkSession)

    return ValueSets(spark_session, jvalue_sets)

def get_hierarchies(spark_session, database='ontologies'):
    """
    Returns a :class:`Hierarchies` instance for the given database.
    """
    jhierarchies = spark_session._jvm.com.cerner.bunsen.mappings \
        .Hierarchies.getFromDatabase(spark_session._jsparkSession, database)

    return Hierarchies(spark_session, jhierarchies)

def create_hierarchies(spark_session):
    """
    Creates a new, empty :class:`Hierarchies` instance.
    """
    jhierarchies = spark_session._jvm.com.cerner.bunsen.mappings \
        .Hierarchies.getEmpty(spark_session._jsparkSession)

    return Hierarchies(spark_session, jhierarchies)

def _add_mappings_to_map(jvm, concept_map, mappings):
    """
    Helper function to add a collection of mappings in the form of a list of
    [(source_system, source_value, target_system, target_value, equivalence)] tuples
    to the given concept map.
    """
    groups = collections.defaultdict(list)

    for (ss, sv, ts, tv, eq) in mappings:
        groups[(ss,ts)].append((sv,tv,eq))

    for (source_system, target_system), values in groups.items():
        group = concept_map.addGroup()

        group.setSource(source_system)
        group.setTarget(target_system)

        for (source_value, target_value, equivalence) in values:
            element = group.addElement()
            element.setCode(source_value)
            target = element.addTarget()
            target.setCode(target_value)

            if equivalence is not None:

                enumerations = jvm.org.hl7.fhir.dstu3.model.Enumerations

                equivEnum = enumerations.ConceptMapEquivalence.fromCode(equivalence)

                target.setEquivalence(equivEnum)

def _add_values_to_value_set(jvm, value_set, values):
    """
    Helper function to add a collection of values in the form of a list of
    [(source, value)] tuples to the given value set.
    """
    inclusions = collections.defaultdict(list)

    for (s, v) in values:
        inclusions[s].append(v)

    for system, values in inclusions.items():
        inclusion = value_set.getCompose().addInclude()

        inclusion.setSystem(system)

        # FHIR expects a non-empty version, so we use the current datetime for
        # ad-hoc value sets
        version = datetime.datetime \
            .now() \
            .replace(microsecond=0) \
            .isoformat(sep=' ')
        inclusion.setVersion(version)

        for value in values:
            inclusion.addConcept().setCode(value) 

class ConceptMaps(object):
    """
    An immutable collection of FHIR Concept Maps to be used to map value sets.
    """

    def __init__(self, spark_session, jconcept_maps):
        self._spark_session = spark_session
        self._jvm = spark_session._jvm
        self._jconcept_maps = jconcept_maps

    def latest_version(self, url):
        """
        Returns the latest version of a map, or None if there is none."
        """
        df = get_maps().where(df.url == functions.lit(url))
        results = df.agg({"version": "max"}).collect()
        return results[0].min if resuls.count() > 0 else None

    def get_maps(self):
        """
        Returns a dataset of FHIR ConceptMaps without the nested mapping content,
        allowing users to explore mapping metadata.

        The mappings themselves are excluded because they can become quite large,
        so users should use the get_mappings method to explore a table of them.
        """
        return DataFrame(self._jconcept_maps.getMaps(), self._spark_session)

    def get_mappings(self, url=None, version=None):
        """
        Returns a dataset of all mappings which may be filtered by an optional
        concept map url and concept map version.
        """
        df = DataFrame(self._jconcept_maps.getMappings(), self._spark_session)

        if url is not None:
            df = df.where(df.url == functions.lit(url))

        if version is not None:
            df = df.where(df.version == functions.lit(version))

        return df

    def get_map_as_xml(self, url, version):
        """
        Returns an XML string containing the specified concept map.
        """
        concept_map = self._jconcept_maps.getConceptMap(url, version)
        return self._jvm.com.cerner.bunsen.python.Functions.resourceToXml(concept_map)

    def with_new_map(self,
                     url,
                     version,
                     source,
                     target,
                     experimental=True,
                     mappings=[]):
        """
        Returns a new ConceptMaps instance with the given map added. Callers
        may include a list of mappings tuples in the form of
        [(source_system, source_value, target_system, target_value, equivalence)].
        """
        concept_map = self._jvm.org.hl7.fhir.dstu3.model.ConceptMap()
        concept_map.setUrl(url)
        concept_map.setVersion(version)
        concept_map.setSource(self._jvm.org.hl7.fhir.dstu3.model.UriType(source))
        concept_map.setTarget(self._jvm.org.hl7.fhir.dstu3.model.UriType(target))

        if (experimental):
            concept_map.setExperimental(True)

        _add_mappings_to_map(self._jvm, concept_map, mappings)

        map_as_list = self._jvm.java.util.Collections.singletonList(concept_map)

        return ConceptMaps(self._spark_session,
                           self._jconcept_maps.withConceptMaps(map_as_list))

    def add_mappings(self, url, version, mappings):
        """
        Returns a new ConceptMaps instance with the given mappings added to an existing map.
        The mappings parameter must be a list of tuples of the form
        [(source_system, source_value, target_system, target_value, equivalence)].
        """
        concept_map = self._jconcept_maps.getConceptMap(url, version)

        _add_mappings_to_map(self._jvm, concept_map, mappings)

        map_as_list = self._jvm.java.util.Collections.singletonList(concept_map)

        return ConceptMaps(self._spark_session,
                           self._jconcept_maps.withConceptMaps(map_as_list))

    def write_to_database(self, database):
        """
        Writes the mapping content to the given database, creating a mappings
        and conceptmaps table if they don't exist.
        """
        self._jconcept_maps.writeToDatabase(database)

class ValueSets(object):
    """
    An immutable collection of FHIR Value Sets to be used to for
    ontologically-based queries.
    """

    def __init__(self, spark_session, jvalue_sets):
        self._spark_session = spark_session
        self._jvm = spark_session._jvm
        self._jvalue_sets = jvalue_sets

    def latest_version(self, url):
        """
        Returns the latest version of a value set, or None if there is none.
        """
        df = get_value_sets().where(df.url == functions.lit(url))
        results = df.agg({"valueSetVersion": "max"}).collect()
        return results[0].min if results.count() > 0 else None

    def get_value_sets(self):
        """
        Returns a dataset of FHIR ValueSets without the nested value content,
        allowing users to explore value set metadata.

        The values themselves are excluded because they can be become quite
        large, so users should use the get_values method to explore them.
        """
        return DataFrame(self._jvalue_sets.getValueSets(), self._spark_session)

    def get_values(self, url=None, version=None):
        """
        Returns a dataset of all values which may be filtered by an optional
        value set url and value set version.
        """
        df = DataFrame(self._jvalue_sets.getValues(), self._spark_session)

        if  url is not None:
            df = df.where(df.valueSetUri == functions.lit(url))

        if version is not None:
            df = df.where(df.valueSetVersion == functions.lit(url))

        return df

    def get_value_set_as_xml(self, url, version):
        """
        Returns an XML string containing the specified value set.
        """
        value_set = self._jvalue_sets.getValueSet(url, version)
        return self._jvm.com.cerner.bunsen.python.Functions.resourceToXml(value_set)

    def with_new_value_set(self,
                           url,
                           version,
                           experimental=True,
                           values=[]):
        """
        Returns a new ValueSets instance with the given value set added. Callers
        may include a list of value tuples in the form of [(system, value)].
        """
        value_set = self._jvm.org.hl7.fhir.dstu3.model.ValueSet()
        value_set.setUrl(url)
        value_set.setVersion(version)
        
        if (experimental):
            value_set.setExperimental(True)

        _add_values_to_value_set(self._jvm, value_set, values)

        value_set_as_list = self._jvm.java.util.Collections.singletonList(value_set)

        return ValueSets(self._spark_session,
                         self._jvalue_sets.withValueSets(value_set_as_list))

    def add_values(self, url, version, values):
        """
        Returns a new ValueSets instance with the given values added to an
        existing value set. The values parameter must be a list of the form
        [(sytem, value)].
        """
        value_set = self._jvalue_sets.getValueSet(url, version)

        _add_values_to_value_set(self._jvm, value_set, values)
        
        value_set_as_list = self._jvm.java.util.Collections.singletonList(value_set)

        return ValueSets(self._spark_session,
                         self._jvalue_sets.withValueSets(value_set_as_list))

    def write_to_database(self, database):
        """
        Writes the value set content to the given database, creating a values
        and valuesets table if they don't exist.
        """
        self._jvalue_sets.writeToDatabase(database)

class Hierarchies(object):
    """
    An immutable collection of values from hierarchical code systems to be used
    for ontologically-based queries.
    """

    def __init__(self, spark_session, jhierarchies):
        self._spark_session = spark_session
        self._jvm = spark_session._jvm
        self._jhierarchies = jhierarchies

    def latest_version(self, uri):
        """
        Returns the latest version of a hierarchy, or None if there is none.
        """
        df = get_ancestors().where(df.uri == functions.lit(uri))
        results = df.agg({"version": "max"}).collect()
        return results[0].min if results.count() > 0 else None

    def get_ancestors(self, url=None, version=None):
        """
        Returns a dataset of ancestor values representing the transitive
        closure of codes in this Hierarchies instance filtered by an optional
        hierarchy uri and version..
        """
        df = DataFrame(self._jhierarchies.getAncestors(), self._spark_session)

        if url is not None:
            df = df.where(df.uri == functions.lit(uri))

        if version is not None:
            df = df.where(df.version == functions.lit(veresion))

        return df

    def write_to_database(self, database):
        """
        Write the ancestor content to the given database, create an ancestors
        table if they don't exist.
        """
        self._jhierarchies.writeToDatabase(database)
