from libs import db
from libs import log

from rainwave.playlist_objects.metadata import AssociatedMetadata
from rainwave.playlist_objects.metadata import make_searchable_string

class Artist(AssociatedMetadata):
	select_by_name_query = "SELECT artist_id AS id, artist_name AS name, artist_name_searchable AS name_searchable FROM r4_artists WHERE artist_name = %s"
	select_by_id_query = "SELECT artist_id AS id, artist_name AS name, artist_name_searchable AS name_searchable FROM r4_artists WHERE artist_id = %s"
	select_by_song_id_query = "SELECT r4_artists.artist_id AS id, r4_artists.artist_name AS name, r4_artists.artist_name_searchable AS name_searchable, r4_song_artist.artist_is_tag AS is_tag, artist_order AS \"order\" FROM r4_song_artist JOIN r4_artists USING (artist_id) WHERE song_id = %s ORDER BY artist_order"
	disassociate_song_id_query = "DELETE FROM r4_song_artist WHERE song_id = %s AND artist_id = %s"
	associate_song_id_query = "INSERT INTO r4_song_artist (song_id, artist_id, artist_is_tag, artist_order) VALUES (%s, %s, %s, %s)"
	has_song_id_query = "SELECT COUNT(song_id) FROM r4_song_artist WHERE song_id = %s AND artist_id = %s"
	check_self_size_query = "SELECT COUNT(song_id) FROM r4_song_artist JOIN r4_songs USING (song_id) WHERE artist_id = %s AND song_verified = TRUE"
	delete_self_query = "DELETE FROM r4_artists WHERE artist_id = %s"

	# needs to be specialized because of artist_order
	def associate_song_id(self, song_id, is_tag = None, order = None):
		if not order and (not "order" in self.data or not self.data['order']):
			order = db.c.fetch_var("SELECT MAX(artist_order) FROM r4_song_artist WHERE song_id = %s", (song_id,))
			if not order:
				order = -1
			order += 1
		elif not order:
			order = self.data['order']
		self.data['order'] = order
		if is_tag == None:
			is_tag = self.is_tag
		else:
			self.is_tag = is_tag
		if db.c.fetch_var(self.has_song_id_query, (song_id, self.id)) > 0:
			pass
		else:
			if not db.c.update(self.associate_song_id_query, (song_id, self.id, is_tag, order)):
				raise MetadataUpdateError("Cannot associate song ID %s with %s ID %s" % (song_id, self.__class__.__name__, self.id))

	def _insert_into_db(self):
		self.id = db.c.get_next_id("r4_artists", "artist_id")
		return db.c.update("INSERT INTO r4_artists (artist_id, artist_name, artist_name_searchable) VALUES (%s, %s, %s)", (self.id, self.data['name'], make_searchable_string(self.data['name'])))

	def _update_db(self):
		return db.c.update("UPDATE r4_artists SET artist_name = %s, artist_name_searchable = %s WHERE artist_id = %s", (self.data['name'], make_searchable_string(self.data['name']), self.id))

	def _start_cooldown_db(self, sid, cool_time):
		# Artists don't have cooldowns on Rainwave.
		pass

	def _start_election_block_db(self, sid, num_elections):
		# Artists don't block elections either (OR DO THEY)
		pass

	def load_all_songs(self, sid, user_id = None):
		# I'm not going to provide a list of Song objects here because the overhead of that would spiral out of control
		# You may think you can do this in a smaller or easier statement, but there's actually a number of challenges here
		# 1. Users can request from the results of this query, so the origin_sid doesn't matter as much as "does it exist on that station"
		# 2. Users can open albums from this page, which means the album ID and album name MUST match and if it's available on
		#       the request station it must be opened to the relevant album ON THAT STATION (not what it may be assigned to on another)
		requestable = True if user_id else False
		self.data['songs'] = db.c.fetch_all(
			"SELECT r4_song_artist.song_id AS id, r4_songs.song_origin_sid AS sid, MAX(song_title) AS title, MAX(song_rating) AS rating, "
				"BOOL_OR(CASE WHEN r4_song_sid.sid = %s THEN %s ELSE FALSE END) AS requestable, "
				"MAX(CASE WHEN r4_song_sid.sid = %s THEN album_id ELSE NULL END) AS real_album_id, "
				"MAX(CASE WHEN r4_song_sid.sid = %s THEN album_name ELSE NULL END) AS real_album_name, "
				"MAX(album_name) AS album_name, MAX(album_id) AS album_id, "
				"MAX(song_length) AS length, "
				"BOOL_OR(CASE WHEN r4_song_sid.sid = %s THEN song_cool ELSE FALSE END) AS cool, "
				"MAX(CASE WHEN r4_song_sid.sid = %s THEN song_cool_end ELSE 0 END) AS cool_end, "
				"MAX(COALESCE(song_rating_user, 0)) AS rating_user, BOOL_OR(COALESCE(song_fave, FALSE)) AS fave "
			"FROM r4_song_artist "
				"JOIN r4_songs USING (song_id) "
				"JOIN r4_song_sid USING (song_id) "
				"JOIN r4_albums USING (album_id) "
				"LEFT JOIN r4_song_ratings ON (r4_song_artist.song_id = r4_song_ratings.song_id AND r4_song_ratings.user_id = %s) "
			"WHERE r4_song_artist.artist_id = %s AND r4_songs.song_verified = TRUE "
			"GROUP BY r4_song_artist.song_id, r4_songs.song_origin_sid "
			"ORDER BY requestable DESC, album_name, MAX(song_title) ",
			(sid, requestable, sid, sid, sid, sid, user_id, self.id))
		# And of course, now we have to burn extra CPU cycles to make sure the right album name is used and that we present the data
		# in the same format seen everywhere else on the API.  Still, much faster then loading individual song objects.
		for song in self.data['songs']:
			if (song['real_album_id']):
				song['albums'] = [ { "name": song['real_album_name'], "id": song['real_album_id'] } ]
			else:
				song['albums'] = [ { "name": song['album_name'], "id": song['album_id'] } ]
			song.pop('album_name')
			song.pop('album_id')
			song.pop('real_album_name')
			song.pop('real_album_id')