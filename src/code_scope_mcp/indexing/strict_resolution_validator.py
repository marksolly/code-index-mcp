"""
Strict Resolution Validator for Indexing Orchestrator.

This module contains the StrictResolutionValidator class that handles all strict resolution
mode validation and reporting logic, extracted from IndexingOrchestrator to reduce class bloat.
"""
import sqlite3
from typing import List, Tuple, Type


class StrictResolutionValidator:
    """
    Handles strict resolution mode validation and reporting for the indexing orchestrator.

    This class encapsulates all logic related to validating that relationship handlers
    have resolved their relationships in strict mode, including querying the database
    and raising appropriate exceptions with detailed diagnostic information.
    """

    def __init__(self, db_connection: sqlite3.Connection, logger, strict_resolution: bool = False):
        """
        Initialize the strict resolution validator.

        Args:
            db_connection: Database connection for querying unresolved relationships
            logger: Logger instance for diagnostic output
            strict_resolution: Whether strict resolution mode is enabled
        """
        self.db_connection = db_connection
        self.logger = logger
        self.strict_resolution = strict_resolution

    def validate_after_handler(self, handler_class: Type, catch_exceptions: bool) -> None:
        """
        Validate that a relationship handler resolved all its relationships.

        Args:
            handler_class: The handler class that just finished processing
            catch_exceptions: Whether exceptions should be caught and logged instead of raised
        """
        if not self.strict_resolution:
            return

        unresolved_count, unresolved_details = self._get_unresolved_by_resolver(handler_class.__name__)

        if unresolved_count > 0:
            error_msg = f"Handler {handler_class.__name__} left {unresolved_count} unresolved relationship(s) after Phase 3"
            # For catch_exceptions mode, log but continue with generic message
            if catch_exceptions:
                self.logger.log("Orchestrator", f"STRICT MODE VIOLATION: {error_msg}")
                print(f"⚠️  STRICT MODE: {error_msg}")
            else:
                from .exceptions import StrictModeViolationException
                # For non-catch_exceptions mode, raise detailed custom exception
                raise StrictModeViolationException(
                    error_msg,
                    unresolved_relationships=unresolved_details,
                    handler_name=handler_class.__name__
                )

    def validate_final_state(self, catch_exceptions: bool) -> None:
        """
        Perform final validation that all relationship handlers resolved their relationships.

        Args:
            catch_exceptions: Whether exceptions should be caught and logged instead of raised
        """
        if not self.strict_resolution:
            self.logger.mustLog("Orchestrator", "Strict resolution mode is disabled, skipping validation")
            return

        self.logger.mustLog("Orchestrator", "Running strict resolution validation...")

        # Find all unique resolver names from unresolved relationships
        cursor = self.db_connection.cursor()
        try:
            cursor.execute("SELECT DISTINCT target_resolver_name FROM unresolved_relationships WHERE target_resolver_name IS NOT NULL")
            resolver_names = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.mustLog("Orchestrator", f"Error querying resolver names: {e}")
            return
        finally:
            cursor.close()

        if not resolver_names:
            self.logger.mustLog("Orchestrator", "No unresolved relationships with resolver names found")
            return

        violations = []
        all_unresolved_details = []
        for resolver_name in resolver_names:
            unresolved_count = self._count_unresolved_by_resolver(resolver_name)
            if unresolved_count > 0:
                violations.append(f"{resolver_name}: {unresolved_count} unresolved relationship(s)")

        # Collect details for all unresolved relationships
        for resolver_name in resolver_names:
            count, details = self._get_unresolved_by_resolver(resolver_name)
            if count > 0:
                all_unresolved_details.extend(details)

        if violations:
            error_msg = "Handlers left unresolved relationships after Phase 3 completion"

            if not catch_exceptions:
                from .exceptions import StrictModeViolationException
                raise StrictModeViolationException(
                    error_msg,
                    unresolved_relationships=all_unresolved_details
                )
            else:
                violations_msg = "STRICT MODE VIOLATION: " + "\n".join(violations)
                print(f"⚠️  {violations_msg}")
                self.logger.mustLog("Orchestrator", violations_msg)
        else:
            self.logger.mustLog("Orchestrator", "Strict resolution validation passed - no unresolved relationships found")

    def _count_unresolved_by_resolver(self, resolver_name: str) -> int:
        """
        Count unresolved relationships for a specific resolver class.

        Args:
            resolver_name: Name of the resolver/handler to count for

        Returns:
            Number of unresolved relationships
        """
        cursor = self.db_connection.cursor()
        try:
            # Count unresolved relationships where the target_resolver_name matches
            cursor.execute(
                "SELECT COUNT(*) FROM unresolved_relationships WHERE target_resolver_name = ?",
                (resolver_name,)
            )
            count = cursor.fetchone()[0]

            if count > 0:
                self.logger.log("Orchestrator",
                    f"Found {count} unresolved relationships for resolver: {resolver_name}")

            return count
        except Exception as e:
            self.logger.mustLog("Orchestrator",
                f"Error counting unresolved relationships for {resolver_name}: {e}")
            return 0
        finally:
            cursor.close()

    def _get_unresolved_by_resolver(self, resolver_name: str) -> Tuple[int, List[str]]:
        """
        Get count and details of unresolved relationships for a specific resolver class.

        Args:
            resolver_name: Name of the resolver/handler to get details for

        Returns:
            Tuple of (count, list_of_details) where details are human-readable strings
        """
        cursor = None
        try:
            cursor = self.db_connection.cursor()

            # Comprehensive query to get detailed human-readable information about unresolved relationships
            query = """
                SELECT f.language, s1.qname as source_qname, rt.name as rel_type,
                       r.intermediate_symbol_qname, r.target_name, r.target_qname,
                       r.creator_location, r.target_resolver_name
                FROM unresolved_relationships r
                JOIN code_symbols s1 ON r.source_symbol_id = s1.id
                JOIN relationship_types rt ON r.relationship_type_id = rt.id
                JOIN files f ON s1.file_id = f.id
                WHERE r.target_resolver_name = ?
                ORDER BY f.language, source_qname
            """

            cursor.execute(query, (resolver_name,))
            rows = cursor.fetchall()

            count = len(rows)
            details = []

            for row in rows:
                language, source_qname, rel_type, intermediate_symbol_qname, target_name, target_qname, creator_location, target_resolver_name = row

                # Build comprehensive detail string with all meaningful information
                source_display = source_qname or "unknown_source"
                target_display = target_qname or target_name or "unknown_target"

                detail = f"[{language}] {source_display} ──{rel_type}──► {target_display}"

                # Add intermediate symbol info if available
                if intermediate_symbol_qname:
                    detail += f" (via {intermediate_symbol_qname})"

                # Add creator location for debugging
                if creator_location:
                    detail += f" [created in {creator_location}]"

                details.append(detail)

            return count, details
        except Exception as e:
            self.logger.mustLog("Orchestrator",
                f"Error getting unresolved relationships for {resolver_name}: {e}")
            # Fallback to simpler query if JOINs fail
            try:
                cursor = self.db_connection.cursor()
                cursor.execute(
                    "SELECT target_name, intermediate_symbol_qname, creator_location, target_resolver_name "
                    "FROM unresolved_relationships WHERE target_resolver_name = ?",
                    (resolver_name,)
                )
                rows = cursor.fetchall()

                count = len(rows)
                details = []

                for row in rows:
                    target_name, intermediate_symbol_qname, creator_location, target_resolver_name = row
                    detail = f"unresolved {target_name or 'unknown'}"
                    if intermediate_symbol_qname:
                        detail += f" (via {intermediate_symbol_qname})"
                    if creator_location:
                        detail += f" [created in {creator_location}]"
                    details.append(detail)

                return count, details
            except Exception as fallback_error:
                self.logger.mustLog("Orchestrator", f"Error in fallback query for {resolver_name}: {fallback_error}")
                return 0, []
        finally:
            if cursor:
                cursor.close()
