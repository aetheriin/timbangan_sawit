USE TimbanganSawitDB;

select t.id, s.nama, t.nomortiket from
    TransaksiTimbang t join supir s on t.supirid = s.id order by waktumasuk desc ;